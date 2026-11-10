"""Old Norse texts: the Poetic Edda, the Prose Edda, Njáls saga and Egils saga.

  python build_oldnorse.py <sources> <texts.db>

All four are downloads (nothing of Old Norse ships with the app).

  - Poetic Edda: Edward Pettit's edition and translation (2023, CC BY-NC 4.0),
    from its TEI XML (pettit.py), in sources/pettit/. One part per poem, one
    block per stanza (its lines are the segments; a speaker line such as
    "Óðinn kvað:" is a segment of its own), prose passages as paragraphs.
  - Prose Edda (Finnur Jónsson, 1907; Brodeur's translation, 1916), Njáls saga
    (Finnur Jónsson, 1908; Dasent, 1861) and Egils saga (Finnur Jónsson, 1894;
    Green, 1893): the texts and translations built once from the scans by
    non_texts.py and non_translations.py, committed in data/. Cited by
    chapter and paragraph (the Prose Edda by part, chapter and paragraph).
    A chapter's English is divided among its blocks in proportion to the
    Old Norse (the translations follow the text closely, but not paragraph
    for paragraph).

Lemmas and parses: non_forms.py (when its tables are there); otherwise each
word is looked up as written.
"""
import gzip
import json
import os
import sys
from collections import Counter

import oldnorse as on
import pettit

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BLOCK_CHARS = 900            # about this much Old Norse per block in the prose works

POETIC_CREDIT = pettit.CREDIT
SAGA_CREDIT = {
    "njala": ("Text: Finnur Jónsson, Brennu-Njálssaga (Njála), Altnordische Saga-Bibliothek 13 (Halle, 1908), "
              "from the archive.org scan, its OCR corrected for this app against NeuralMIcePaHC (CC BY 4.0). "
              "Translation: George Webbe Dasent, The Story of Burnt Njal (1861), Project Gutenberg. Both public domain."),
    "egils": ("Text: Finnur Jónsson, Egils saga Skallagrímssonar, Altnordische Saga-Bibliothek 3 (Halle, 1894), "
              "from the archive.org scan, its OCR corrected for this app against NeuralMIcePaHC (CC BY 4.0). "
              "Translation: W. C. Green, The Story of Egil Skallagrimsson (1893). Both public domain."),
    "snorra_edda": ("Text: Finnur Jónsson, Edda Snorra Sturlusonar (Reykjavík, 1907), from two archive.org scans, its "
                    "OCR corrected for this app. Translation: Arthur Gilchrist Brodeur, The Prose Edda (1916), for "
                    "the Prologue, Gylfaginning and Skáldskaparmál; Háttatal is untranslated. Both public domain."),
}
EDDA_PARTS = ["Prologus", "Gylfaginning", "Skáldskaparmál", "Háttatal"]


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


class Writer:
    """Inserts a work's blocks, segments and tokens."""

    def __init__(self, db, wid, analyser=None):
        self.db, self.wid, self.analyser = db, wid, analyser
        self.seq = self.bseq = 0
        self.stats = Counter()
        self.analysed = set()

    def block(self, cite_start, cite_end, english):
        bid = self.db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                              " VALUES (?,?,?,?,?,?)", (self.wid, self.bseq, cite_start, cite_end, english, "[]")).lastrowid
        self.bseq += 1
        return bid

    def segment(self, bid, cite, text, line_n=None, heading=None, para_start=1, speaker=None):
        sid = self.db.execute(
            "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (self.wid, bid, self.seq, cite, line_n, speaker, heading, None, para_start, text, "[]")).lastrowid
        self.seq += 1
        for idx, (s, e, w) in enumerate(on.tokenize(text)):
            lemma = key = tag = source = None
            rs = self.analyser.readings(w) if self.analyser else []
            if rs:
                lemma, key, tag = rs[0]
                source = "non-forms"
                self.stats["analysed"] += 1
                if w not in self.analysed:
                    self.analysed.add(w)
                    for rank, (l, k, t) in enumerate(rs):
                        self.db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)",
                                        (on.PREFIX + w, rank, l, k, self.analyser.describe(t)))
            else:                       # looked up as written (a name, or a word the tables lack)
                lemma, key = w, on.key(w)
                self.stats["as written"] += 1
            self.db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                            " VALUES (?,?,?,?,?,?,?,?,?)", (sid, idx, u16(text, s), u16(text, e), w, lemma, key, tag,
                                                             source))
        return sid


def work(db, sort, urn, author, title, kind, form, translator, scope, credit, analyser):
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, urn, author, title, kind, form, urn + ".text", urn + ".english" if translator else "", translator or "",
         scope, "non-forms" if analyser else "", "non", credit)).lastrowid
    return Writer(db, wid, analyser)


# ------------------------------------------------------------- Poetic Edda --
def build_poetic(db, sort, xml_dir, analyser):
    poems = pettit.read(xml_dir)
    w = work(db, sort, "urn:cts:norseLit:edda.poetic", "Poetic Edda", "Poetic Edda", "verse", "poem",
             "Edward Pettit", "complete", POETIC_CREDIT, analyser)
    stanzas = prose = 0
    for p in poems:
        n, heading = p["n"], p["title"]
        k = 0
        for it in p["items"]:
            if it["kind"] == "stanza":
                st = it["n"]
                eng = "\n".join(([it["english_speaker"]] if it.get("english_speaker") else []) + it["english"])
                bid = w.block(f"{n}.{st}", f"{n}.{st}", eng)
                if it.get("speaker"):
                    w.segment(bid, f"{n}.{st}.s", it["speaker"], heading=heading, para_start=1)
                    heading = None
                for li, line in enumerate(it["lines"]):
                    w.segment(bid, f"{n}.{st}" if li == 0 else f"{n}.{st}.{li + 1}", line,
                              line_n=st if li == 0 and st else None, heading=heading,
                              para_start=1 if li == 0 and not it.get("speaker") else 0)
                    heading = None
                stanzas += 1
            else:
                k += 1
                bid = w.block(f"{n}.p{k}", f"{n}.p{k}", it["english"])
                w.segment(bid, f"{n}.p{k}", it["text"], heading=heading, para_start=1)
                heading = None
                prose += 1
    return dict(poems=len(poems), stanzas=stanzas, prose=prose, **w.stats)


# --------------------------------------------------------------- prose works --
def proportional_blocks(items, english, target=BLOCK_CHARS):
    """[(items, english paragraphs)]: the chapter's items in runs of about
    target characters, each with the English paragraphs at the same fraction
    of the chapter's English."""
    size = [len(it.get("text") or " ".join(it["lines"])) for it in items]
    total = sum(size) or 1
    runs, cur, acc = [], [], 0
    for it, s in zip(items, size):
        cur.append(it)
        acc += s
        if acc >= target:
            runs.append(cur)
            cur, acc = [], 0
    if cur:
        if runs and sum(len(it.get("text") or " ".join(it["lines"])) for it in cur) < target / 3:
            runs[-1].extend(cur)          # a short tail joins the run before
        else:
            runs.append(cur)
    elen = [len(p) for p in english]
    etotal = sum(elen) or 1
    cum_e = [sum(elen[:i + 1]) / etotal for i in range(len(english))]
    out, done, ei = [], 0, 0
    for r, run in enumerate(runs):
        done += sum(len(it.get("text") or " ".join(it["lines"])) for it in run)
        frac = done / total
        if r == len(runs) - 1:
            take = len(english)
        else:            # the English paragraph boundary nearest this fraction
            take = min(range(ei, len(english) + 1),
                       key=lambda j: abs((cum_e[j - 1] if j else 0) - frac)) if english else 0
        out.append((run, english[ei:take]))
        ei = max(ei, take)
    return out


def share_english(chapters, english):
    """{chapter: paragraphs}: an undivided translation of several chapters,
    cut at the paragraph boundaries nearest each chapter's share of the text."""
    size = [sum(len(it.get("text") or " ".join(it["lines"])) for it in c["items"]) for c in chapters]
    total, elen = sum(size) or 1, [len(p) for p in english]
    etotal = sum(elen) or 1
    out, ei, done = {}, 0, 0
    for k, (c, s) in enumerate(zip(chapters, size)):
        done += s
        if k == len(chapters) - 1:
            take = len(english)
        else:
            take = min(range(ei, len(english) + 1), key=lambda j: abs(sum(elen[:j]) / etotal - done / total))
        out[c["n"]] = english[ei:take]
        ei = take
    return out


def write_chapter(w, prefix, chapter, english, heading):
    """Blocks and segments of one chapter; cites prefix.chapter.paragraph."""
    n, p = chapter["n"], 0
    for run, eng in proportional_blocks(chapter["items"], english):
        first = p + 1
        bid = w.block(f"{prefix}{n}.{first}", f"{prefix}{n}.{first}", "\n".join(eng))
        for it in run:
            p += 1
            cite = f"{prefix}{n}.{p}"
            if it["kind"] == "prose":
                w.segment(bid, cite, it["text"], heading=heading, para_start=1)
                heading = None
            else:                          # a stanza: a segment per line
                for li, line in enumerate(it["lines"]):
                    w.segment(bid, cite if li == 0 else f"{cite}.{li + 1}", line, heading=heading, para_start=1)
                    heading = None
        db_end = f"{prefix}{n}.{p}"
        w.db.execute("UPDATE block SET cite_end=? WHERE id=?", (db_end, bid))


def build_saga(db, sort, key, urn, title, translations, analyser):
    text = json.load(gzip.open(os.path.join(DATA, "non_texts", f"{key}.json.gz"), "rt"))
    tr = translations[key]
    english = {c["n"]: c["english"] for c in tr["chapters"]}
    w = work(db, sort, urn, "Sagas of Icelanders", title, "prose", "chapters", tr["translator"], "complete",
             SAGA_CREDIT[key], analyser)
    for c in text["chapters"]:
        write_chapter(w, "", c, english.get(c["n"], []), f"Chapter {c['n']}")
    return dict(chapters=len(text["chapters"]), untranslated=[c["n"] for c in text["chapters"] if c["n"] not in english],
                **w.stats)


def build_prose_edda(db, sort, translations, analyser):
    text = json.load(gzip.open(os.path.join(DATA, "non_texts", "snorra_edda.json.gz"), "rt"))
    tr = translations["snorra_edda"]
    w = work(db, sort, "urn:cts:norseLit:edda.snorra", "Snorri Sturluson", "Prose Edda", "prose", "history",
             tr["translator"], "complete", SAGA_CREDIT["snorra_edda"], analyser)
    report = {}
    for part in text["parts"]:
        pn = EDDA_PARTS.index(part["title"]) + 1
        eng = {c["n"]: c["english"] for c in tr["parts"].get(part["title"], [])}
        if part["title"] == "Prologus":                    # Brodeur's Prologue is not divided: share it out
            eng = share_english(part["chapters"], eng.get(1, []))
        heading = part["title"]
        for c in part["chapters"]:
            write_chapter(w, f"{pn}.", c, eng.get(c["n"], []), heading if heading else None)
            heading = None
        report[part["title"]] = dict(chapters=len(part["chapters"]),
                                     translated=sum(1 for c in part["chapters"] if eng.get(c["n"])))
    report.update(w.stats)
    return report


def corpus_words(xml_dir):
    """Every word of the four texts (for the form tables and their ranking)."""
    words = []

    def take(texts):
        for t in texts:
            words.extend(w for _, _, w in on.tokenize(t))
    if os.path.isdir(xml_dir):
        for p in pettit.read(xml_dir):
            for it in p["items"]:
                take(it["lines"] if it["kind"] == "stanza" else [it["text"]])
    for name in ("njala", "egils", "snorra_edda"):
        d = json.load(gzip.open(os.path.join(DATA, "non_texts", f"{name}.json.gz"), "rt"))
        chapters = d.get("chapters") or [c for p in d["parts"] for c in p["chapters"]]
        for c in chapters:
            for it in c["items"]:
                take([it["text"]] if it["kind"] == "prose" else it["lines"])
    return words


def main(sources, out):
    import sqlite3
    db = sqlite3.connect(out)
    sort = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    translations = json.load(gzip.open(os.path.join(DATA, "non_translations.json.gz"), "rt"))
    report = {}
    xml_dir = os.path.join(sources, "pettit", "XML-edition")
    zoega = os.path.join(sources, "zoega", "json", "zoega.json")
    analyser = None
    if os.path.exists(zoega):
        import non_forms
        words = corpus_words(xml_dir)
        analyser = non_forms.Analyser.build(zoega, words)
        analyser.train(words)
    else:
        print(f"note: {zoega} not found; words are looked up as written", file=sys.stderr)
    if os.path.isdir(xml_dir):
        report["Poetic Edda"] = build_poetic(db, sort, xml_dir, analyser)
    else:
        print(f"note: {xml_dir} not found; leaving out the Poetic Edda", file=sys.stderr)
    report["Prose Edda"] = build_prose_edda(db, sort + 1, translations, analyser)
    report["Njáls saga"] = build_saga(db, sort + 2, "njala", "urn:cts:norseLit:saga.njals", "Njáls saga",
                                      translations, analyser)
    report["Egils saga"] = build_saga(db, sort + 3, "egils", "urn:cts:norseLit:saga.egils", "Egils saga",
                                      translations, analyser)
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
