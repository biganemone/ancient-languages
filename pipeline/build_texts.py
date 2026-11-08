"""Build texts.db: works, aligned Greek/English blocks, display segments,
tokens with parses (treebank where available, otherwise Morpheus).

Usage: python build_texts.py <canonical-greekLit/data> <treebank v2.1 Greek/texts> <out.db>
"""
import difflib
import json
import os
import re
import sqlite3
import sys
from collections import Counter

import greek
import morpheus
import tei
from works import WORKS

SCHEMA = """
CREATE TABLE work (
  id INTEGER PRIMARY KEY, sort INT, urn TEXT, author TEXT, title TEXT, kind TEXT, form TEXT,
  greek_urn TEXT, english_urn TEXT, translator TEXT, scope TEXT, parse_source TEXT,
  language TEXT DEFAULT 'grc', credit TEXT);
-- All offsets (token start/end, marker positions) are UTF-16 code units, to
-- match NSString/UITextView indexing in the app.
-- An alignment unit: Greek segments + the English passage that translates them.
CREATE TABLE block (
  id INTEGER PRIMARY KEY, work_id INT, seq INT, cite_start TEXT, cite_end TEXT,
  english TEXT, english_markers TEXT);
-- A Greek display unit: a verse line, or a paragraph/speech (piece) in prose.
--   heading: printed above this segment (book title, "strophe 1", …)
--   part:    I/M/F for a verse line shared between speakers
--   para_start: 0 = prose continuation of the previous segment across a
--               section break (the app may join them)
CREATE TABLE segment (
  id INTEGER PRIMARY KEY, work_id INT, block_id INT, seq INT, cite TEXT,
  line_n INT, speaker TEXT, heading TEXT, part TEXT, para_start INT, text TEXT, markers TEXT);
CREATE TABLE token (
  id INTEGER PRIMARY KEY, segment_id INT, idx INT, start INT, "end" INT,
  form TEXT, lemma TEXT, lemma_key TEXT, postag TEXT, source TEXT,
  word_id INT);  -- shared by the pieces of a word broken across lines (Coptic codices)
-- The morphemes of a Coptic bound group (one written word), in order.
CREATE TABLE morph (token_id INT, rank INT, form TEXT, lemma TEXT, lemma_key TEXT, pos TEXT);
CREATE INDEX morph_token ON morph(token_id);
-- Possible analyses (Morpheus) for words without treebank data, ranked.
CREATE TABLE analysis (form TEXT, rank INT, lemma TEXT, lemma_key TEXT, parse TEXT);
CREATE INDEX token_seg ON token(segment_id);
CREATE INDEX seg_block ON segment(block_id);
CREATE INDEX seg_work ON segment(work_id, seq);
CREATE INDEX block_work ON block(work_id, seq);
CREATE INDEX analysis_form ON analysis(form);
"""

report = {}


def u16(text, i):
    """Python (code point) offset -> UTF-16 offset."""
    return len(text[:i].encode("utf-16-le")) // 2


def markers16(text, markers):
    return [[u16(text, o), u, n] for o, u, n in markers]


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def line_number(n):
    m = re.match(r"\d+", n or "")
    return int(m.group(0)) if m else None


# ------------------------------------------------------------------ English --
def english_events(root, keep_speakers=True):
    """Flatten an English translation to events: text, para breaks,
    milestones (line / card / section), book starts, speaker labels."""
    events = []

    def walk(el):
        name = tei.local(el.tag)
        if name in ("note", "bibl", "head", "reg"):
            pass
        elif name == "div" and (el.get("subtype") or "").lower() == "commentary":   # a translator's introduction
            pass
        elif name == "milestone":
            events.append(("ms", (el.get("unit") or "").lower(), el.get("n")))
        elif name in ("speaker", "label"):
            if keep_speakers:
                events.append(("para",))
                events.append(("text", clean("".join(el.itertext())).rstrip(".:") + ". "))
        else:
            if name == "div" and (el.get("subtype") or "").lower() in ("book", "card") and el.get("n"):
                events.append(("ms", el.get("subtype").lower(), el.get("n")))
            if name == "l" and el.get("n"):
                events.append(("ms", "line", el.get("n")))
            if name in ("sp", "said", "p"):
                events.append(("para",))
            if el.text:
                events.append(("text", el.text))
            for child in el:
                walk(child)
            if name in ("p", "sp", "said"):
                events.append(("para",))
        if el.tail:
            events.append(("text", el.tail))

    body = tei.find_all(root, "body")[0]
    walk(body)
    return events


def cut_english(events, unit, book_filter=None):
    """Split English events at milestones of `unit`. Returns a list of
    (book, n, text, markers) in document order."""
    pieces, buf, book, n = [], [], None, None

    def flush():
        if buf:
            text, ms = tei.assemble(buf)
            if text:
                pieces.append((book, n, text, ms))

    for ev in events:
        if ev[0] == "ms" and ev[1] == "book":
            flush()
            buf, book, n = [], ev[2], None
        elif ev[0] == "ms" and ev[1] == unit and ev[2]:
            flush()
            buf, n = [], ev[2]
        else:
            buf.append(ev)
    flush()
    if book_filter:
        pieces = [p for p in pieces if p[0] in book_filter]
    return pieces


# -------------------------------------------------------------------- Verse --
def greek_lines(root, form):
    """Greek verse lines in order: dicts with book, n, text, para, speaker,
    heading, part."""
    lines = []
    state = dict(book=None, speaker=None, heading=None, para=False)

    def walk(el):
        name = tei.local(el.tag)
        sub = (el.get("subtype") or "").lower()
        if name == "div" and sub == "book":
            state["book"] = el.get("n")
            state["heading"] = f"Book {el.get('n')}"
        elif name == "div" and sub in ("strophe", "antistrophe", "epode", "ephymnion", "ephymn"):
            n = el.get("n")
            sub = "ephymnion" if sub == "ephymn" else sub
            state["heading"] = f"{sub} {n}" if n else sub
            state["para"] = True
        elif name == "div" and sub in ("choral", "episode", "anapests", "lyric", "kommos",
                                       "trochees", "iambics", "close"):
            state["para"] = True
        if name == "sp":
            state["speaker"] = None
            state["para"] = True
        if name == "speaker":
            state["speaker"] = clean("".join(el.itertext()))
            return
        if name == "l":
            text, ms = tei.assemble(tei.element_events(el))
            para = state["para"] or any(u == "para" for _, u, _ in ms)
            lines.append(dict(book=state["book"], n=el.get("n"), text=text, para=para,
                              speaker=state["speaker"], heading=state["heading"],
                              part=(el.get("part") or None)))
            state.update(speaker=None, heading=None, para=False)
            return
        if name == "milestone" and (el.get("unit") or "").lower() == "para":
            state["para"] = True
        for child in el:
            walk(child)

    walk(tei.find_all(root, "body")[0])
    return lines


def verse_blocks(work, data):
    g = tei.parse(path(data, work, "greek"))
    e = tei.parse(path(data, work, "english"))
    lines = greek_lines(g, work["form"])
    books = work.get("books")
    if books:
        lines = [l for l in lines if l["book"] in books]
    unit = "line" if work["blocks"] == "line5" else "card"
    pieces = cut_english(english_events(e, keep_speakers=work["form"] == "drama"), unit, books)

    # Group English pieces per book; each starts at a Greek line number.
    starts = {}
    for book, n, text, ms in pieces:
        if n is None:   # text before the first milestone of a book: attach to line 1
            n = "1"
        starts.setdefault(book, []).append((line_number(n) or 0, text))

    # Each Greek line belongs to the last English cut at or before it. The cut
    # index never goes backwards (editions transpose lines), and cuts that no
    # line reaches are merged into the next block.
    import bisect
    english_by_book = {b: sorted(v, key=lambda c: c[0]) for b, v in starts.items()}
    blocks, current, prev_book, prev_k = [], None, object(), -1
    for line in lines:
        bk = line["book"]
        cuts = english_by_book.get(bk, [])
        n = line_number(line["n"]) or 0
        k = bisect.bisect_right([c[0] for c in cuts], n) - 1
        if bk != prev_book:
            prev_k = -1
        k = max(k, prev_k, 0 if cuts else -1)
        if bk != prev_book or k != prev_k or current is None:
            english = "\n\n".join(t for _, t in cuts[prev_k + 1:k + 1]) if cuts else ""
            current = dict(lines=[], english=english, book=bk, k=k)
            blocks.append(current)
        current["lines"].append(line)
        prev_book, prev_k = bk, k
    # English after the last block's cut (no Greek line reached it)
    last_k = {}
    for b in blocks:
        last_k[b["book"]] = b
    for bk, b in last_k.items():
        rest = [t for _, t in english_by_book.get(bk, [])[b["k"] + 1:]]
        if rest:
            b["english"] = "\n\n".join([b["english"]] + rest).strip()

    out = []
    for b in blocks:
        cite = lambda l: f"{l['book']}.{l['n']}" if l["book"] else l["n"]
        out.append(dict(cite_start=cite(b["lines"][0]), cite_end=cite(b["lines"][-1]),
                        english=b["english"], english_markers=[],
                        segments=[dict(cite=cite(l), line_n=line_number(l["n"]), speaker=l["speaker"],
                                       heading=l["heading"], part=l["part"], para=l["para"],
                                       text=l["text"], markers=[]) for l in b["lines"]]))
    report.setdefault(work["title"], {}).update(
        lines=len(lines), blocks=len(out),
        block_sizes=dict(Counter(min(len(b["segments"]), 40) for b in out).most_common(5)))
    return out


# -------------------------------------------------------------------- Prose --
def prose_events(root, skip_reg=True):
    """Greek or English prose as events, with section/book milestones,
    paragraph breaks and speaker labels."""
    events = []

    def walk(el):
        name = tei.local(el.tag)
        if name in ("note", "bibl", "head") or (name == "reg" and skip_reg):
            pass                # reg: gazetteer text in Godley's place names (but Clark's Cicero: "quo")
        elif name == "div" and (el.get("subtype") or "").lower() == "commentary":   # a translator's introduction
            pass
        elif name == "milestone":
            unit = (el.get("unit") or "").lower()
            if unit in ("section", "para"):
                events.append(("ms", unit, el.get("n")))
        elif name == "label":
            events.append(("speaker", clean("".join(el.itertext()))))
        else:
            sub = (el.get("subtype") or "").lower()
            if name == "div" and sub in ("book", "letter", "speech"):      # (speech: Cicero's In Catilinam)
                events.append(("book", el.get("n")))
            elif name == "div" and sub == "chapter":       # Herodotus: book / chapter / section
                events.append(("chapter", el.get("n")))
            elif name == "div" and sub == "section" and el.get("n"):
                events.append(("ms", "section", el.get("n")))
            if name in ("p", "said"):
                events.append(("para",))
            if el.text:
                events.append(("text", el.text))
            for child in el:
                walk(child)
            if name in ("p", "said"):
                events.append(("para",))
        if el.tail:
            events.append(("text", el.tail))

    walk(tei.find_all(root, "body")[0])
    return events


def prose_units(events):
    """Cut prose events into (book, chapter, section, para_start, speaker, text)
    pieces: a new piece at every paragraph/speech start and at every section."""
    pieces, buf = [], []
    state = dict(book=None, chapter=None, section=None, speaker=None, para=True)

    def flush(next_para):
        text, _ = tei.assemble(buf)
        if text.strip():
            pieces.append(dict(book=state["book"], chapter=state["chapter"], section=state["section"],
                               para=state["para"], speaker=state["speaker"], text=text))
            state.update(para=next_para, speaker=None)
        else:
            state["para"] = state["para"] or next_para
        buf.clear()

    for ev in events:
        if ev[0] == "book":
            flush(True)
            state.update(book=ev[1], chapter=None)
        elif ev[0] == "chapter":
            flush(True)
            state.update(chapter=ev[1], section=None)
        elif ev[0] == "para" or (ev[0] == "ms" and ev[1] == "para"):
            flush(True)
        elif ev[0] == "ms" and ev[1] == "section":
            flush(False)
            state["section"] = ev[2]
        elif ev[0] == "speaker":
            flush(True)
            state["speaker"] = ev[1]
        else:
            buf.append(ev)
    flush(True)
    return pieces


def prose_blocks(work, data):
    skip_reg = not work.get("keep_reg")
    g = prose_units(prose_events(tei.parse(path(data, work, "greek")), skip_reg))
    e = prose_units(prose_events(tei.parse(path(data, work, "english")), skip_reg))
    books = work.get("books")
    if books:
        g = [p for p in g if p["book"] in books]
        e = [p for p in e if p["book"] in books]

    chapters = work["blocks"] == "chapter"     # Herodotus: a block per chapter
    by_english = work["blocks"] == "english"   # Josephus: a block per English chunk

    if by_english:
        # each English chunk is numbered by the Greek section it starts at;
        # Greek sections belong to the last chunk that started at or before them
        starts = {(p["book"], p["section"]) for p in e}
        current = None
        for p in g:
            if (p["book"], p["section"]) in starts or current is None or current[0] != p["book"]:
                current = (p["book"], p["section"])
            p["block"] = current
        for p in e:
            p["block"] = (p["book"], p["section"])

    # Herodotus, Thucydides: the English has the same sections as the Greek,
    # so a block per section (the smallest unit both sides share)
    by_section = chapters and work.get("section_blocks")

    def key(p):
        if by_english:
            return p["block"]
        if by_section:
            return (p["book"], p["chapter"], p["section"] or "1")
        return (p["book"], p["chapter"]) if chapters else (p["book"], p["section"])

    if not chapters and not by_english and not work.get("plain_sections"):
        # some milestones give a bare Stephanus page ("328"): its first section
        for p in g + e:
            if p["section"] and re.fullmatch(r"\d+", p["section"]):
                p["section"] += "a"

    english = {}
    for p in e:
        label = (p["speaker"].rstrip(".:") + ". ") if p["speaker"] else ""
        # no space before punctuation (left behind by dropped place-name glosses)
        text = label + re.sub(r"\s+([,.;:!?)])", r"\1", p["text"])
        if key(p) in english:
            # Thucydides (Crawley): a paragraph per section, run on like the Greek chapter
            run_on = work.get("run_on_english") and not p["speaker"]
            english[key(p)] += ("\n\n" if p["para"] and not run_on else " ") + text
        else:
            english[key(p)] = text

    blocks, order = {}, []
    for p in g:
        k = key(p)
        if k not in blocks:
            blocks[k] = []
            order.append(k)
        blocks[k].append(p)

    if by_section:
        # an English section the Greek numbers differently (Herodotus 6.11.4
        # where the Greek has 6.11.3; "pr" for the proem, 0): it joins the
        # Greek section at or before it in the same chapter
        def num(x):
            m = re.match(r"\d+", x)
            return int(m.group()) if m else 0
        for k in [k for k in english if k not in blocks]:
            same = sorted((num(g[2]), g) for g in blocks if g[:2] == k[:2])
            if not same:
                continue
            before = [g for n, g in same if n <= num(k[2])]
            target = before[-1] if before else same[0][1]
            text = english.pop(k)
            english[target] = english[target] + " " + text if target in english else text

    out = []
    missing = 0
    first_of_book = set()
    unit = work.get("unit", "Book")
    last_chapter = None
    for k in order:
        book = k[0]
        if k not in english:
            missing += 1
        segs = []
        previous_section = None
        for i, p in enumerate(blocks[k]):
            heading = None
            if book and book not in first_of_book:
                heading = f"{unit} {book}"
                first_of_book.add(book)
            if chapters:
                # cite book.chapter.section; the number shown is "chapter.section"
                # at a chapter's start, then just the section
                section = p["section"] or "1"
                cite = f"{book}.{p['chapter']}.{section}" if book else f"{p['chapter']}.{section}"
                chapter_start = (book, p["chapter"]) != last_chapter
                last_chapter = (book, p["chapter"])
                # (section 1 is the chapter's start; 0 is Herodotus' proem)
                if chapter_start:
                    marker = [[0, "section", p["chapter"]]]
                elif section != previous_section and section not in ("0", "1"):
                    marker = [[0, "section", section]]
                else:
                    marker = []
                previous_section = section
            elif by_english:
                # cite book.section (Niese); the block's first section in the
                # gutter, later ones inline
                section = p["section"]
                cite = f"{book}.{section}"
                marker = [[0, "section", section]] if i == 0 or section != previous_section else []
                previous_section = section
            else:
                section = k[1]
                cite = f"{book}.{section}" if book else section
                marker = [[0, "section", section]] if i == 0 else []
            # Herodotus: a chapter is one paragraph; its sections run on
            if chapters:
                para = chapter_start or bool(p["speaker"])
            else:
                para = (i == 0 or bool(p["speaker"])) if by_english else p["para"]
            segs.append(dict(cite=cite, line_n=None, speaker=p["speaker"], heading=heading, part=None,
                             para=para, text=p["text"], markers=marker))
        out.append(dict(cite_start=segs[0]["cite"], cite_end=segs[-1]["cite"], english=english.get(k, ""),
                        english_markers=[], segments=segs))
    report.setdefault(work["title"], {}).update(
        sections=len(out), sections_without_english=missing,
        english_sections_unmatched=len(set(english) - set(blocks)))
    return out


# ------------------------------------------------------------------ Parses --
def treebank_words(tbdir, filename, books=None):
    root = tei.parse(f"{tbdir}/{filename}")
    words = []
    for w in tei.find_all(root, "word"):
        tag = w.get("postag") or ""
        form = w.get("form") or ""
        if tag.startswith("u") or not form or (form.startswith("[") and form.endswith("]")):
            continue
        cite = (w.get("cite") or "").split(":")[-1]
        words.append(dict(form=form, lemma=w.get("lemma"), postag=tag, cite=cite))
    return words


def gorman_words(files):
    """Vanessa Gorman's treebanks: Arethusa XML like the AGDT, but the
    citation is on the sentence ("1.21.401": book first)."""
    gdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources", "gorman", "xml versions")
    words = []
    for f in files:
        root = tei.parse(os.path.join(gdir, f))
        for sentence in tei.find_all(root, "sentence"):
            cite = sentence.get("subdoc") or ""
            for w in tei.find_all(sentence, "word"):
                tag = w.get("postag") or ""
                form = w.get("form") or ""
                if tag.startswith("u") or not form or (form.startswith("[") and form.endswith("]")) \
                        or w.get("insertion_id") or w.get("artificial"):
                    continue
                words.append(dict(form=form, lemma=w.get("lemma"), postag=tag, cite=cite))
    return words


def attach_treebank(tokens, words, label):
    a = [greek.bare(t["form"]) for t in tokens]
    b = [greek.bare(w["form"]) for w in words]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    c = Counter()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                tokens[i1 + k].update(morph=words[j1 + k], source="treebank")
            c["exact"] += i2 - i1
        elif op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                tokens[i1 + k].update(morph=words[j1 + k], source="treebank")
            c["variant"] += i2 - i1
        else:
            # the treebank sometimes splits one written word in two (οὐδέ -> οὐ + δέ)
            i, j = i1, j1
            while i < i2 and j + 1 < j2:
                if a[i] == b[j] + b[j + 1]:
                    w2 = words[j + 1]
                    tokens[i].update(source="treebank", morph=dict(
                        lemma=greek.compound_lemma(tokens[i]["form"], w2["form"], w2["lemma"]),
                        postag=w2["postag"]))
                    c["split"] += 1
                    i, j = i + 1, j + 2
                else:
                    break
            c["unmatched"] += i2 - i
    return c


_frequency = None


def lemma_frequency(tbdir):
    """How often each lemma occurs across all treebanks: used to rank
    Morpheus's alternative analyses (λέγω before λέγος)."""
    global _frequency
    if _frequency is None:
        from works import treebank_files
        _frequency = Counter()
        for f in treebank_files():
            for w in treebank_words(tbdir, f):
                if w["lemma"]:
                    _frequency[greek.lex_key(re.sub(r"\d+$", "", w["lemma"]))] += 1
    return _frequency


def tokens_for(text, segment_index):
    return [dict(seg=segment_index, idx=i, start=u16(text, st), end=u16(text, en), form=form)
            for i, (st, en, form) in enumerate(greek.tokenize(text))]


# ------------------------------------------------------------------- Write --
def path(data, work, which):
    if work.get(f"{which}_file"):          # a text kept in pipeline/data (Long's Marcus Aurelius)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), work[f"{which}_file"])
    group, w = work["work"].split(".")
    return f"{data}/{group}/{w}/{work['work']}.{work[which]}.xml"


def part_blocks(work, data):
    """A work made of several texts (the Homeric Hymns): each text's blocks,
    with citations prefixed by its number ("2.123") and a heading."""
    out = []
    for part in work["parts"]:
        blocks = verse_blocks(dict(work, work=part["work"], title=f"{work['title']} {part['n']}"), data)
        for b in blocks:
            b["cite_start"] = f"{part['n']}.{b['cite_start']}"
            b["cite_end"] = f"{part['n']}.{b['cite_end']}"
            for s in b["segments"]:
                s["cite"] = f"{part['n']}.{s['cite']}"
        if blocks and blocks[0]["segments"]:
            blocks[0]["segments"][0]["heading"] = part["heading"]
        out.extend(blocks)
    return out


def build_work(db, sort, work, data, tbdir):
    if work.get("parts"):
        blocks = part_blocks(work, data)
    else:
        blocks = verse_blocks(work, data) if work["kind"] == "verse" else prose_blocks(work, data)
    segments, tokens = [], []
    for b in blocks:
        for s in b["segments"]:
            segments.append(s)
            tokens.extend(tokens_for(s["text"], len(segments) - 1))

    stats = Counter()
    for part in work.get("parts") or []:
        if part.get("treebank"):    # align each treebanked part on its own
            prefix = part["n"] + "."
            toks = [t for t in tokens if segments[t["seg"]]["cite"].startswith(prefix)]
            stats.update(attach_treebank(toks, treebank_words(tbdir, part["treebank"]), work["title"]))
    if work.get("treebank"):
        words = treebank_words(tbdir, work["treebank"])
        if work["form"] == "epic":   # align book by book (keeps difflib fast)
            by_book = {}
            for t in tokens:
                book = segments[t["seg"]]["cite"].split(".")[0]
                by_book.setdefault(book, []).append(t)
            for book, toks in by_book.items():
                stats.update(attach_treebank(toks, [w for w in words if w["cite"].split(".")[0] == book],
                                             work["title"]))
        elif work.get("treebank_book"):   # the treebank covers one book (Herodotus 1)
            prefix = work["treebank_book"] + "."
            toks = [t for t in tokens if segments[t["seg"]]["cite"].startswith(prefix)]
            stats.update(attach_treebank(toks, words, work["title"]))
        else:
            stats.update(attach_treebank(tokens, words, work["title"]))

    if work.get("gorman"):   # Gorman's treebanks: align book by book (a work without books at once)
        def book_of(cite):
            return cite.split(".")[0] if "." in cite else ""
        words = gorman_words(work["gorman"])
        for book in sorted({book_of(w["cite"]) for w in words}):
            toks = [t for t in tokens if book_of(segments[t["seg"]]["cite"]) == book]
            stats.update(attach_treebank(toks, [w for w in words if book_of(w["cite"]) == book],
                                         work["title"]))

    # Morpheus for everything the treebank didn't cover
    need = sorted({t["form"] for t in tokens if "morph" not in t})
    analyses = morpheus.analyses(need, work["dialect"], lemma_frequency(tbdir)) if need else {}
    for t in tokens:
        if "morph" in t:
            continue
        found = analyses.get(t["form"]) or []
        if found:
            t.update(source="morpheus", morph=dict(lemma=found[0][0], postag=None))
            stats["morpheus"] += 1
        else:
            stats["no_parse"] += 1

    scope = "Book " + ", ".join(work["books"]) if work.get("books") else "complete"
    parse_source = "treebank" if work.get("treebank") or work.get("gorman") or any(p.get("treebank") for p in work.get("parts") or []) \
        else "morpheus"
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sort, f"urn:cts:greekLit:{work['work']}", work["author"], work["title"], work["kind"], work["form"],
         f"urn:cts:greekLit:{work['work']}.{work['greek']}",
         f"urn:cts:greekLit:{work['work']}.{work['english']}", work["translator"], scope,
         parse_source)).lastrowid

    seg_ids, seq = [], 0
    for bi, b in enumerate(blocks):
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)",
                         (wid, bi, b["cite_start"], b["cite_end"], b["english"],
                          json.dumps(markers16(b["english"], b["english_markers"])))).lastrowid
        for s in b["segments"]:
            seg_ids.append(db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, s["cite"], s["line_n"], s["speaker"], s["heading"], s["part"],
                 int(bool(s["para"])), s["text"], json.dumps(markers16(s["text"], s["markers"])))).lastrowid)
            seq += 1
    for t in tokens:
        m = t.get("morph") or {}
        lemma = m.get("lemma")
        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                   ' VALUES (?,?,?,?,?,?,?,?,?)',
                   (seg_ids[t["seg"]], t["idx"], t["start"], t["end"], t["form"], lemma,
                    greek.lex_key(re.sub(r"\d+$", "", lemma)) if lemma else None,
                    m.get("postag"), t.get("source")))
    for form, rows in analyses.items():
        for rank, (lemma, parse) in enumerate(rows):
            db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)",
                       (form, rank, lemma, greek.lex_key(lemma), parse))

    total = len(tokens)
    report.setdefault(work["title"], {}).update(
        tokens=total, parses={k: f"{100 * v / max(total, 1):.1f}%" for k, v in stats.items()})


def main(data, tbdir, out, only=None):
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    for sort, work in enumerate(WORKS):
        if only and work["title"] not in only:
            continue
        build_work(db, sort, work, data, tbdir)
        print(f"built {work['title']}", file=sys.stderr)
    # analyses can repeat across works; keep one copy per (form, rank)
    db.execute("DELETE FROM analysis WHERE rowid NOT IN (SELECT MIN(rowid) FROM analysis GROUP BY form, rank)")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:] or None)
