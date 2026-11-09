"""Add Latin texts to texts.db: Vergil's Aeneid and the Clementine Vulgate,
and the verse map that lets a Vulgate book be read in parallel with the
Septuagint or the Greek New Testament.

Usage: python build_latin.py <sources dir> <texts.db>
  (run after build_lxx.py and build_nt.py: the parallel map needs them)

- Aeneid: Perseus (Greenough's text, Theodore C. Williams's translation),
  laid out like Homer with Perseus's English "cards". Parses: the Perseus
  Latin treebank for 6.1–295, Morpheus (Latin) for the rest.
- Vulgate: the Clementine Vulgate and the Douay-Rheims (Challoner) English,
  same versification (scrollmapper/bible_databases). A work per book, a part
  per chapter, a block per verse, like the NT and LXX. Parses: the PROIEL
  treebank (Jerome's Vulgate, CC BY-NC-SA 4.0) where it covers the NT,
  Morpheus elsewhere.
- Parallel map (table `parallel`): each Vulgate verse block -> the LXX / NT
  verse block(s) with the same content, and back. Verse numbers differ in
  many places (Jeremiah, Esther, the Psalm titles, Nehemiah = 2 Esdras 11–23,
  Baruch 6 = Letter of Jeremiah …), so verses are aligned through their
  English (Douay-Rheims against Brenton / the BSB): length, shared words and
  matching numbers, with verses the in-order alignment misplaces moved to
  their best match.
"""
import csv
import difflib
import glob
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

import latin
import latin_homer
import morpheus
import tei
from build_texts import prose_blocks, verse_blocks

SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


# ------------------------------------------------------------- Treebanks --
def proiel_tokens(path):
    """[(citation, form, lemma, postag)] from a PROIEL XML file."""
    out = []
    root = tei.parse(path)
    for t in tei.find_all(root, "token"):
        form = t.get("form")
        if not form or t.get("empty-token-sort"):
            continue
        out.append((t.get("citation-part") or "", form, t.get("lemma") or "",
                    latin.proiel_postag(t.get("part-of-speech"), t.get("morphology"))))
    return out


def agldt_words(path):
    """AGLDT (Perseus Latin treebank) words: [(cite, form, lemma, postag)],
    cite from the sentence's subdoc ("6.12")."""
    out = []
    root = tei.parse(path)
    for s in tei.find_all(root, "sentence"):
        cite = s.get("subdoc") or ""
        for w in tei.find_all(s, "word"):
            tag = w.get("postag") or ""
            form = w.get("form") or ""
            if not form or tag.startswith("u") or w.get("insertion_id") or w.get("artificial"):
                continue
            out.append((cite, form, w.get("lemma") or "", tag))
    return out


def lemma_frequency(sources):
    c = Counter()
    for f in glob.glob(f"{sources}/syntacticus/proiel/*.xml"):
        if os.path.basename(f) in ("latin-nt.xml", "caes-gal.xml", "cic-att.xml", "cic-off.xml"):
            for _c, _f, lemma, _t in proiel_tokens(f):
                c[latin.key(lemma)] += 1
    return c


def attach(tokens, words):
    """Align treebank words to our tokens by form; returns how many matched."""
    a = [latin.key(t["form"]) for t in tokens]
    b = [latin.key(w[1]) for w in words]
    n = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("equal", "replace") and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                w = words[j1 + k]
                tokens[i1 + k].update(lemma=w[2], postag=w[3], source="treebank")
            n += i2 - i1
    return n


# ------------------------------------------------- other Perseus Latin texts --
PERSEUS_LATIN = [
    dict(work="phi0448.phi001", title="Gallic War", author="Caesar", greek="perseus-lat2", english="perseus-eng2",
         kind="prose", form="history", blocks="chapter", translator="W. A. McDevitte and W. S. Bohn",
         proiel="caes-gal.xml",
         credit="Text (ed. T. Rice Holmes, 1914; Book 8 by Aulus Hirtius) and translation (W. A. McDevitte and "
                "W. S. Bohn, 1869) from the Perseus Digital Library (CC BY-SA). Parses: the PROIEL treebank "
                "(Dag Haug et al., CC BY-NC-SA 4.0) for much of Books 1–6, Morpheus for the rest."),
    dict(work="phi0959.phi006", title="Metamorphoses", author="Ovid", greek="perseus-lat2", english="perseus-eng3",
         kind="verse", form="epic", blocks="card", translator="Brookes More",
         treebank="phi0959.phi006.perseus-lat1.tb.xml",
         credit="Text (ed. Hugo Magnus, 1892) and translation (Brookes More, 1922) from the Perseus Digital "
                "Library (CC BY-SA). Parses: Perseus Latin Dependency Treebank (parts of Book 1) and Morpheus."),
    dict(work="phi0474.phi013", title="In Catilinam", author="Cicero", greek="perseus-lat2", english="perseus-eng2",
         kind="prose", form="speeches", blocks="section", plain_sections=True, unit="Speech",
         translator="C. D. Yonge", treebank="phi0474.phi013.perseus-lat1.tb.xml",
         credit="Text (ed. A. C. Clark, 1908) and translation (C. D. Yonge, 1856) from the Perseus Digital "
                "Library (CC BY-SA). Parses: Perseus Latin Dependency Treebank (parts of Speeches 1–2) and "
                "Morpheus."),
    dict(work="phi0474.phi052", title="De Amicitia", author="Cicero", greek="perseus-lat2", english="perseus-eng2",
         kind="prose", form="sections", blocks="section", plain_sections=True, translator="W. A. Falconer",
         credit="Text and translation (W. A. Falconer, Loeb, 1923) from the Perseus Digital Library (CC BY-SA). "
                "Parses: Morpheus."),
    dict(work="phi1351.phi001", title="Agricola", author="Tacitus", greek="perseus-lat2", english="perseus-eng4",
         kind="prose", form="chapters", blocks="chapter", translator="A. J. Church and W. J. Brodribb",
         credit="Text (ed. Henry Furneaux, 1899) and translation (A. J. Church and W. J. Brodribb, 1877) from "
                "the Perseus Digital Library (CC BY-SA). Parses: Morpheus."),
    dict(work="phi1351.phi002", title="Germania", author="Tacitus", greek="perseus-lat2", english="perseus-eng2",
         kind="prose", form="chapters", blocks="chapter", translator="A. J. Church and W. J. Brodribb",
         credit="Text (ed. Henry Furneaux, 1899) and translation (A. J. Church and W. J. Brodribb, 1877) from "
                "the Perseus Digital Library (CC BY-SA). Parses: Morpheus."),
    dict(work="phi1351.phi005", title="Annals", author="Tacitus", greek="perseus-lat2", english="perseus-eng2",
         kind="prose", form="history", blocks="chapter", books=["1"], translator="A. J. Church and W. J. Brodribb",
         scope="Book 1",
         # (the treebank file named for the Annals, phi1351.phi005, is in fact Histories 1)
         credit="Text (ed. C. D. Fisher, 1906) and translation (A. J. Church and W. J. Brodribb, 1869) from the "
                "Perseus Digital Library (CC BY-SA). Parses: Morpheus."),
]


def perseus_latin_files():
    """Paths in canonical-latinLit and treebank_data that PERSEUS_LATIN needs."""
    out = []
    for w in PERSEUS_LATIN:
        group, work = w["work"].split(".")
        out += [f"data/{group}/{work}/{w['work']}.{w['greek']}.xml", f"data/{group}/{work}/{w['work']}.{w['english']}.xml"]
    return out


def build_perseus_latin(db, sort, sources, frequency, w):
    data = f"{sources}/canonical-latinLit/data"
    w = dict(w, keep_reg=True)              # Latin <reg> is the text itself
    blocks = verse_blocks(w, data) if w["kind"] == "verse" else prose_blocks(w, data)
    treebank = None
    if w.get("proiel"):                    # PROIEL (Caesar): citations "1.1.1"
        by_book = defaultdict(list)
        for word in proiel_tokens(f"{sources}/syntacticus/proiel/{w['proiel']}"):
            by_book[word[0].split(".")[0]].append(word)
        treebank = list(by_book.items())
    elif w.get("treebank"):
        words = agldt_words(f"{sources}/treebank_data/v2.1/Latin/texts/{w['treebank']}")
        if w.get("treebank_whole"):
            treebank = [(None, words)]
        else:
            by_book = defaultdict(list)
            for word in words:
                by_book[word[0].split(".")[0]].append(word)
            treebank = list(by_book.items())
    meta = dict(urn=f"urn:cts:latinLit:{w['work']}", greek_urn=f"urn:cts:latinLit:{w['work']}.{w['greek']}",
                author=w["author"], title=w["title"], kind=w["kind"], form=w["form"],
                english_urn=f"urn:cts:latinLit:{w['work']}.{w['english']}", translator=w["translator"],
                parse_source="treebank" if treebank else "morpheus", credit=w["credit"], scope=w.get("scope"))
    return insert_work(db, sort, meta, blocks, frequency, treebank)


# ---------------------------------------------------------------- Writing --
OLD_SPELLINGS = [("y", "i"), ("œ", "e"), ("Œ", "E"), ("mt", "mpt"), ("ll", "l"), ("cle", "cli"), ("quenq", "quemq"),
                 ("cæ", "ce"), ("æ", "e")]


def old_spelling_variants(form):
    """Modern spellings to try for a form Morpheus doesn't know (each change, then all)."""
    out = []
    for old, new in OLD_SPELLINGS:
        if old in form:
            out.append(form.replace(old, new))
    allc = form
    for old, new in OLD_SPELLINGS:
        allc = allc.replace(old, new)
    if allc != form:
        out.append(allc)
    return list(dict.fromkeys(out))


def insert_work(db, sort, meta, blocks, frequency, treebank=None):
    """blocks: [dict(cite_start, cite_end, english, segments=[dict(cite, line_n,
    heading, para, text, markers)])]. treebank: [(book or None, words)].
    Returns stats."""
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, meta["urn"], meta["author"], meta["title"], meta["kind"], meta["form"], meta.get("greek_urn", meta["urn"]),
         meta.get("english_urn", ""), meta["translator"], meta.get("scope") or "complete", meta["parse_source"], "lat",
         meta["credit"])).lastrowid
    tokens, seq, block_ids = [], 0, []
    for bi, b in enumerate(blocks):
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)",
                         (wid, bi, b["cite_start"], b["cite_end"], b["english"], "[]")).lastrowid
        block_ids.append(bid)
        for s in b["segments"]:
            sid = db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, s["cite"], s.get("line_n"), s.get("speaker"), s.get("heading"), s.get("part"),
                 1 if s.get("para") else 0, s["text"], json.dumps(s.get("markers") or []))).lastrowid
            seq += 1
            for idx, (a, e, form) in enumerate(latin.tokenize(s["text"])):
                tokens.append(dict(seg=sid, idx=idx, start=u16(s["text"], a), end=u16(s["text"], e), form=form,
                                   cite=s["cite"]))
    stats = Counter()
    for book, words in treebank or []:
        toks = [t for t in tokens if book is None or t["cite"].split(".")[0] == book]
        stats["treebank"] += attach(toks, words)
    need = sorted({t["form"] for t in tokens if "lemma" not in t})
    analyses = morpheus.latin_analyses(need, frequency) if need else {}
    # older spellings (the Didot Homer's inclytus, ocyus, cœna, promtus): try the modern one
    variants = {f: old_spelling_variants(f) for f in need if not analyses.get(f)}
    variants = {f: v for f, v in variants.items() if v}
    if variants:
        extra = morpheus.latin_analyses(sorted({x for vs in variants.values() for x in vs}), frequency)
        for f, vs in variants.items():
            for x in vs:
                if extra.get(x):
                    analyses[f] = extra[x]
                    break
    for t in tokens:
        if "lemma" not in t:
            found = analyses.get(t["form"]) or []
            if found:
                t.update(lemma=found[0][0], postag=None, source="morpheus")
                stats["morpheus"] += 1
            elif t["form"][:1].isupper():         # a name: look it up as written
                t.update(lemma=t["form"], postag=None, source=None)
                stats["name"] += 1
            else:
                stats["no_parse"] += 1
        # homograph numbers (sum1, caelum2) only split one dictionary word in two
        lemma = re.sub(r"\d+$", "", t["lemma"]) if t.get("lemma") else None
        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (t["seg"], t["idx"], t["start"], t["end"], t["form"], lemma,
                    latin.key(lemma) if lemma else None, t.get("postag"), t.get("source")))
    for form, rows in analyses.items():
        seen = []
        for lemma, parse in rows:
            row = (re.sub(r"\d+$", "", lemma), parse)
            if row not in seen:
                seen.append(row)
        for rank, (lemma, parse) in enumerate(seen):
            db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)", (form, rank, lemma, latin.key(lemma), parse))
    total = max(1, len(tokens))
    return wid, block_ids, dict(tokens=len(tokens), blocks=len(blocks),
                                treebank=f"{100 * stats['treebank'] / total:.1f}%",
                                names=stats["name"],
                                unparsed=f"{100 * stats['no_parse'] / total:.1f}%")


# ----------------------------------------------------------------- Aeneid --
def build_aeneid(db, sort, sources, frequency):
    data = f"{sources}/canonical-latinLit/data"
    work = dict(work="phi0690.phi003", title="Aeneid", greek="perseus-lat2", english="perseus-eng2",
                kind="verse", form="epic", blocks="card")
    blocks = verse_blocks(work, data)
    tb = agldt_words(f"{sources}/treebank_data/v2.1/Latin/texts/phi0690.phi003.perseus-lat1.tb.xml")
    by_book = defaultdict(list)
    for w in tb:
        by_book[w[0].split(".")[0]].append(w)
    meta = dict(urn="urn:cts:latinLit:phi0690.phi003", greek_urn="urn:cts:latinLit:phi0690.phi003.perseus-lat2",
                author="Vergil", title="Aeneid", kind="verse", form="epic",
                english_urn="urn:cts:latinLit:phi0690.phi003.perseus-eng2", translator="Theodore C. Williams",
                parse_source="treebank",
                credit="Text (ed. J. B. Greenough, 1900) and translation (Theodore C. Williams, 1910) from the "
                       "Perseus Digital Library (CC BY-SA). Parses: Perseus Latin Dependency Treebank (6.1–295) "
                       "and Morpheus.")
    return insert_work(db, sort, meta, blocks, frequency, list(by_book.items()))


# ---------------------------------------------------------------- Vulgate --
# (CSV book name, title, PROIEL code, Greek companion(s): [(work title, chapter filter)])
OT = [
    ("Genesis", "Genesis", None, [("Genesis", None)]), ("Exodus", "Exodus", None, [("Exodus", None)]),
    ("Leviticus", "Leviticus", None, [("Leviticus", None)]), ("Numbers", "Numbers", None, [("Numbers", None)]),
    ("Deuteronomy", "Deuteronomy", None, [("Deuteronomy", None)]), ("Joshua", "Joshua", None, [("Joshua", None)]),
    ("Judges", "Judges", None, [("Judges", None)]), ("Ruth", "Ruth", None, [("Ruth", None)]),
    ("I Samuel", "1 Kings (1 Samuel)", None, [("1 Kingdoms (1 Samuel)", None)]),
    ("II Samuel", "2 Kings (2 Samuel)", None, [("2 Kingdoms (2 Samuel)", None)]),
    ("I Kings", "3 Kings (1 Kings)", None, [("3 Kingdoms (1 Kings)", None)]),
    ("II Kings", "4 Kings (2 Kings)", None, [("4 Kingdoms (2 Kings)", None)]),
    ("I Chronicles", "1 Chronicles", None, [("1 Chronicles", None)]),
    ("II Chronicles", "2 Chronicles", None, [("2 Chronicles", None)]),
    ("Ezra", "Ezra", None, [("2 Esdras (Ezra–Nehemiah)", (1, 10))]),
    ("Nehemiah", "Nehemiah", None, [("2 Esdras (Ezra–Nehemiah)", (11, 23))]),
    ("Tobit", "Tobit", None, [("Tobit", None)]), ("Judith", "Judith", None, [("Judith", None)]),
    ("Esther", "Esther", None, [("Esther", None)]), ("Job", "Job", None, [("Job", None)]),
    ("Psalms", "Psalms", None, [("Psalms", None)]), ("Proverbs", "Proverbs", None, [("Proverbs", None)]),
    ("Ecclesiastes", "Ecclesiastes", None, []),
    ("Song of Solomon", "Song of Songs", None, [("Song of Songs", None)]),
    ("Wisdom", "Wisdom", None, [("Wisdom of Solomon", None)]), ("Sirach", "Sirach", None, [("Sirach", None)]),
    ("Isaiah", "Isaiah", None, [("Isaiah", None)]), ("Jeremiah", "Jeremiah", None, [("Jeremiah", None)]),
    ("Lamentations", "Lamentations", None, [("Lamentations", None)]),
    ("Baruch", "Baruch", None, [("Baruch", None), ("Letter of Jeremiah", None)]),
    ("Ezekiel", "Ezekiel", None, [("Ezekiel", None)]),
    ("Daniel", "Daniel", None, [("Daniel (Theodotion)", None), ("Susanna (Theodotion)", None),
                                ("Bel and the Dragon (Theodotion)", None)]),
    ("Hosea", "Hosea", None, [("Hosea", None)]), ("Joel", "Joel", None, [("Joel", None)]),
    ("Amos", "Amos", None, [("Amos", None)]), ("Obadiah", "Obadiah", None, [("Obadiah", None)]),
    ("Jonah", "Jonah", None, [("Jonah", None)]), ("Micah", "Micah", None, [("Micah", None)]),
    ("Nahum", "Nahum", None, [("Nahum", None)]), ("Habakkuk", "Habakkuk", None, [("Habakkuk", None)]),
    ("Zephaniah", "Zephaniah", None, [("Zephaniah", None)]), ("Haggai", "Haggai", None, [("Haggai", None)]),
    ("Zechariah", "Zechariah", None, [("Zechariah", None)]), ("Malachi", "Malachi", None, [("Malachi", None)]),
    ("I Maccabees", "1 Maccabees", None, [("1 Maccabees", None)]),
    ("II Maccabees", "2 Maccabees", None, [("2 Maccabees", None)]),
]
NT = [("Matthew", "MATT"), ("Mark", "MARK"), ("Luke", "LUKE"), ("John", "JOHN"), ("Acts", "ACTS"),
      ("Romans", "ROM"), ("I Corinthians", "1COR"), ("II Corinthians", "2COR"), ("Galatians", "GAL"),
      ("Ephesians", "EPH"), ("Philippians", "PHIL"), ("Colossians", "COL"), ("I Thessalonians", "1THESS"),
      ("II Thessalonians", "2THESS"), ("I Timothy", "1TIM"), ("II Timothy", "2TIM"), ("Titus", "TIT"),
      ("Philemon", "PHILEM"), ("Hebrews", "HEB"), ("James", "JAS"), ("I Peter", "1PET"), ("II Peter", "2PET"),
      ("I John", "1JOHN"), ("II John", "2JOHN"), ("III John", "3JOHN"), ("Jude", "JUDE"),
      ("Revelation of John", "REV")]


def nt_title(name):
    t = re.sub(r"^III ", "3 ", re.sub(r"^II ", "2 ", re.sub(r"^I ", "1 ", name)))
    return "Revelation" if t == "Revelation of John" else t


VULGATE_CREDIT = ("Latin: the Clementine Vulgate; English: the Douay-Rheims Bible, Challoner revision (both "
                  "public domain; from scrollmapper/bible_databases). Parses: the PROIEL treebank, Jerome's "
                  "Vulgate (Dag Haug et al., CC BY-NC-SA 4.0) for most of the NT; Morpheus elsewhere.")


def read_csv(path):
    books = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            books[r["Book"]].append((r["Chapter"], r["Verse"], r["Text"].strip()))
    return books


# --------------------------------------------------------------- Alignment --
STOP = set("""a an the and or but of to in on at by for with from as is are was were be been being it its this
that these those he she they them his her their him i me my we us our you your thou thee thy ye not no shall will
would should may might must do does did have has had which who whom what when where so than then there here all
also into upon unto out up said saith say lord god unto""".split())


def stems(text):
    return {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in STOP}


def align_verses(A, B):
    """A, B: [(key, english)]. Returns for each A index the B indices that
    translate the same text. A monotonic alignment (lengths, shared words,
    matching numbers), then verses it places badly move to their best match
    anywhere in the book (reordered books: Jeremiah, Esther, Proverbs)."""
    n, m = len(A), len(B)
    if not n or not m:
        return [[] for _ in A]
    LA = [len(t) for _, t in A]
    LB = [len(t) for _, t in B]
    SA = [stems(t) for _, t in A]
    SB = [stems(t) for _, t in B]
    ratio = (sum(LB) + 1) / (sum(LA) + 1)

    def sim(i, j):
        if not SA[i] or not SB[j]:
            return 0.0
        return len(SA[i] & SB[j]) / math.sqrt(len(SA[i]) * len(SB[j]))

    def lc(la, lb):
        return abs(math.log((lb + 20) / (ratio * la + 20))) * 1.5

    band = max(60, abs(n - m) + 40)
    cost = {(0, 0): 0.0}
    back = {}
    for i in range(n + 1):
        centre = i * m / n
        for j in range(max(0, int(centre - band)), min(m, int(centre + band)) + 1):
            if i == 0 and j == 0:
                continue
            best, how = math.inf, None
            for di, dj, pen in ((1, 1, 0.0), (1, 0, 2.5), (0, 1, 2.5), (1, 2, 0.8), (2, 1, 0.8)):
                pi, pj = i - di, j - dj
                prev = cost.get((pi, pj))
                if prev is None:
                    continue
                c = prev + pen
                if di and dj:
                    c += lc(sum(LA[pi:i]), sum(LB[pj:j]))
                    c -= 1.5 * max(sim(a, b) for a in range(pi, i) for b in range(pj, j))
                    if di == 1 and dj == 1 and A[pi][0] == B[pj][0]:
                        c -= 0.4
                if c < best:
                    best, how = c, (di, dj)
            if how:
                cost[(i, j)] = best
                back[(i, j)] = how
    owner = [[] for _ in range(n)]
    if (n, m) not in back:
        return owner
    i, j = n, m
    while i > 0 or j > 0:
        di, dj = back[(i, j)]
        if di:
            for a in range(i - di, i):
                owner[a].extend(range(j - dj, j))
        i, j = i - di, j - dj
    # repair: badly placed verses go to their best match
    for i in range(n):
        cur = max((sim(i, j) for j in owner[i]), default=0.0)
        if cur >= 0.3:
            continue
        best = max(range(m), key=lambda j: sim(i, j))
        if sim(i, best) >= 0.35 and sim(i, best) > 2 * cur:
            owner[i] = [best]
    return [sorted(set(o)) for o in owner]


def greek_verses(db, title, chapters):
    """[(block id, key, english, para_start)] of a Greek work, optionally
    only chapters lo..hi."""
    row = db.execute("SELECT id FROM work WHERE title = ? AND (language IS NULL OR language = 'grc')",
                     (title,)).fetchone()
    if not row:
        return []
    out = []
    for bid, cite, english, para in db.execute(
            "SELECT b.id, b.cite_start, b.english, (SELECT s.para_start FROM segment s WHERE s.block_id = b.id "
            "ORDER BY s.seq LIMIT 1) FROM block b WHERE b.work_id = ? ORDER BY b.seq", (row[0],)):
        c = cite.split(".")[0]
        if chapters and not (chapters[0] <= int(re.match(r"\d+", c).group()) <= chapters[1]):
            continue
        out.append((bid, cite, english or "", para))
    return out


def build_vulgate(db, start_sort, sources, frequency, report):
    latin_books = read_csv(f"{sources}/bible_databases/formats/csv/VulgClementine.csv")
    english_books = read_csv(f"{sources}/bible_databases/formats/csv/DRC.csv")
    proiel = defaultdict(list)
    for cite, form, lemma, tag in proiel_tokens(f"{sources}/syntacticus/proiel/latin-nt.xml"):
        code, _, ref = cite.partition(" ")
        proiel[code].append((ref.replace(".", ".", 1), form, lemma, tag))
    books = [(name, title, None, comp, "ot") for name, title, _p, comp in OT] + \
            [(name, nt_title(name), code, [(nt_title(name), None)], "nt") for name, code in NT]
    pairs = []
    for i, (name, title, code, companions, testament) in enumerate(books):
        verses = latin_books.get(name, [])
        english = {(c, v): t for c, v, t in english_books.get(name, [])}
        # the Greek companion's verses, for the parallel map and for paragraphs
        greek = []
        for gtitle, chapters in companions:
            greek.extend(greek_verses(db, gtitle, chapters))
        owner = align_verses([(f"{c}.{v}", english.get((c, v), "")) for c, v, _ in verses],
                             [(g[1], g[2]) for g in greek])
        poetic = name in ("Psalms", "Proverbs", "Song of Solomon", "Job", "Lamentations")
        blocks, prev_chapter = [], None
        for k, (c, v, text) in enumerate(verses):
            mapped = [greek[j] for j in owner[k]]
            heading = None
            if c != prev_chapter:
                heading = f"Psalm {c}" if name == "Psalms" else f"Chapter {c}"
            para = c != prev_chapter or poetic or bool(mapped and mapped[0][3])
            prev_chapter = c
            blocks.append(dict(cite_start=f"{c}.{v}", cite_end=f"{c}.{v}", english=english.get((c, v), ""),
                               segments=[dict(cite=f"{c}.{v}", heading=heading, para=para, text=text,
                                              markers=[[0, "section", v]])]))
        tb = []
        if code and proiel.get(code):
            tb = [(None, [(ref, form, lemma, tag) for ref, form, lemma, tag in proiel[code]])]
        meta = dict(urn=f"urn:vulgate:{i + 1:02d}", author="Vulgate", title=title, kind="prose", form="bible",
                    translator="Douay-Rheims (Challoner)", parse_source="treebank" if tb else "morpheus",
                    credit=VULGATE_CREDIT)
        wid, block_ids, stats = insert_work(db, start_sort + i, meta, blocks, frequency, tb)
        for k, js in enumerate(owner):
            for j in js:
                pairs.append((block_ids[k], greek[j][0]))
        stats.update(greek_verses=len(greek), paired=sum(1 for o in owner if o))
        report[f"Vulgate {title}"] = stats
    # the map, both ways
    db.execute("CREATE TABLE IF NOT EXISTS parallel (block_id INT, other_block_id INT)")
    db.executemany("INSERT INTO parallel VALUES (?,?)", pairs + [(b, a) for a, b in pairs])
    db.execute("CREATE INDEX IF NOT EXISTS parallel_block ON parallel(block_id)")


def main(sources, out):
    db = sqlite3.connect(out)
    cols = [r[1] for r in db.execute("PRAGMA table_info(work)")]
    for col in ("language", "credit"):
        if col not in cols:
            db.execute(f"ALTER TABLE work ADD COLUMN {col} TEXT")
    frequency = lemma_frequency(sources)
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report = {}
    _wid, _b, report["Aeneid"] = build_aeneid(db, start, sources, frequency)
    build_vulgate(db, start + 1, sources, frequency, report)
    sort = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    for i, w in enumerate(PERSEUS_LATIN):
        _wid, _b, report[w["title"]] = build_perseus_latin(db, sort + i, sources, frequency, w)
    # the Didot Latin Homer, block for block with the Greek (latin_homer.py), and its map to the Greek
    sort = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    pairs = []
    for i, w in enumerate(latin_homer.WORKS):
        shaped = latin_homer.blocks_for(db, w)
        if not shaped:
            continue
        meta = dict(urn=w["urn"], author="Homer", title=w["title"], kind="verse", form="epic",
                    translator="A. T. Murray", parse_source="morpheus", credit=latin_homer.CREDIT)
        _wid, block_ids, report[w["title"]] = insert_work(db, sort + i, meta, [b for _, b in shaped], frequency)
        pairs += [(lb, gb) for lb, (gb, _) in zip(block_ids, shaped)]
    db.execute("CREATE TABLE IF NOT EXISTS parallel (block_id INT, other_block_id INT)")
    db.executemany("INSERT INTO parallel VALUES (?,?)", pairs + [(b, a) for a, b in pairs])
    db.execute("DELETE FROM analysis WHERE rowid NOT IN (SELECT MIN(rowid) FROM analysis GROUP BY form, rank)")
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
