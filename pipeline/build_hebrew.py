"""The Hebrew Bible: the Westminster Leningrad Codex with the Open Scriptures
Hebrew Bible's lemmas and morphology (CC BY 4.0), the Berean Standard Bible
as English (public domain), and verse links to the Septuagint and the Vulgate.

  python build_hebrew.py <sources> <texts.db>      (after build_lxx.py and build_latin.py)

- One block per verse, books in the Tanakh's order, grouped as Torah,
  Prophets and Writings. Paragraphs follow the codex's open and closed
  sections (פ, ס).
- Each word is a token; its morphemes (prefixes, the word, suffixes) are
  morph rows, shown as "the parts of this word" like Coptic's. The token's
  lemma is the word's own (not a prefix's).
- Ketiv/qere: the written form, then the read form in brackets.
- English: the BSB verse(s) for each Hebrew verse, through the codex's map
  to English versification (morphhb VerseMap.xml: Malachi 3:19-24 = 4:1-6,
  psalm titles, Joel 3-4 …).
- Parallels: Hebrew verse <-> LXX and Vulgate verses, aligned through their
  English (build_latin.align_verses).
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

from lxml import etree

import hebrew
from build_latin import OT, align_verses

OSIS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"
CREDIT = ("Hebrew: the Westminster Leningrad Codex (public domain) with lemmas and morphology from the "
          "Open Scriptures Hebrew Bible (CC BY 4.0). English: Berean Standard Bible (public domain).")

# (OSIS id, English title, BSB/CSV name, section)
BOOKS = [
    ("Gen", "Genesis", "Genesis", "Torah"), ("Exod", "Exodus", "Exodus", "Torah"),
    ("Lev", "Leviticus", "Leviticus", "Torah"), ("Num", "Numbers", "Numbers", "Torah"),
    ("Deut", "Deuteronomy", "Deuteronomy", "Torah"),
    ("Josh", "Joshua", "Joshua", "Prophets"), ("Judg", "Judges", "Judges", "Prophets"),
    ("1Sam", "1 Samuel", "I Samuel", "Prophets"), ("2Sam", "2 Samuel", "II Samuel", "Prophets"),
    ("1Kgs", "1 Kings", "I Kings", "Prophets"), ("2Kgs", "2 Kings", "II Kings", "Prophets"),
    ("Isa", "Isaiah", "Isaiah", "Prophets"), ("Jer", "Jeremiah", "Jeremiah", "Prophets"),
    ("Ezek", "Ezekiel", "Ezekiel", "Prophets"), ("Hos", "Hosea", "Hosea", "Prophets"),
    ("Joel", "Joel", "Joel", "Prophets"), ("Amos", "Amos", "Amos", "Prophets"),
    ("Obad", "Obadiah", "Obadiah", "Prophets"), ("Jonah", "Jonah", "Jonah", "Prophets"),
    ("Mic", "Micah", "Micah", "Prophets"), ("Nah", "Nahum", "Nahum", "Prophets"),
    ("Hab", "Habakkuk", "Habakkuk", "Prophets"), ("Zeph", "Zephaniah", "Zephaniah", "Prophets"),
    ("Hag", "Haggai", "Haggai", "Prophets"), ("Zech", "Zechariah", "Zechariah", "Prophets"),
    ("Mal", "Malachi", "Malachi", "Prophets"),
    ("Ps", "Psalms", "Psalms", "Writings"), ("Prov", "Proverbs", "Proverbs", "Writings"),
    ("Job", "Job", "Job", "Writings"), ("Song", "Song of Songs", "Song of Solomon", "Writings"),
    ("Ruth", "Ruth", "Ruth", "Writings"), ("Lam", "Lamentations", "Lamentations", "Writings"),
    ("Eccl", "Ecclesiastes", "Ecclesiastes", "Writings"), ("Esth", "Esther", "Esther", "Writings"),
    ("Dan", "Daniel", "Daniel", "Writings"), ("Ezra", "Ezra", "Ezra", "Writings"),
    ("Neh", "Nehemiah", "Nehemiah", "Writings"), ("1Chr", "1 Chronicles", "I Chronicles", "Writings"),
    ("2Chr", "2 Chronicles", "II Chronicles", "Writings"),
]


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


class Lexicon:
    """Headwords for the text's lemmas: augmented Strong's -> lexical index
    entry (Hebrew headword, gloss, BDB id)."""

    def __init__(self, lexdir):
        ns = "{http://openscriptures.github.com/morphhb/namespace}"
        aug = etree.parse(os.path.join(lexdir, "AugIndex.xml")).getroot()
        self.aug = {w.get("aug"): w.text for w in aug.iter(ns + "w")}
        li = etree.parse(os.path.join(lexdir, "LexicalIndex.xml")).getroot()
        self.entries = {}
        for e in li.iter(ns + "entry"):
            w = e.find(ns + "w")
            d = e.find(ns + "def")
            x = e.find(ns + "xref")
            self.entries[e.get("id")] = dict(word=w.text if w is not None else None,
                                             gloss=d.text if d is not None else None,
                                             bdb=x.get("bdb") if x is not None else None,
                                             strong=x.get("strong") if x is not None else None)
        st = etree.parse(os.path.join(lexdir, "HebrewStrong.xml")).getroot()
        self.strong = {}
        for e in st.iter():
            if local(e.tag) == "entry" and e.get("id"):
                w = next((c for c in e if local(c.tag) == "w"), None)
                self.strong[e.get("id")] = w.text if w is not None else None

    def headword(self, lemma):
        l = re.sub(r"[\s+]", "", lemma)
        if l in hebrew.PARTICLES:
            return hebrew.PARTICLES[l][0]
        e = self.entries.get(self.aug.get(l, ""))
        if e and e["word"]:
            return e["word"]
        n = re.match(r"\d+", l)
        return self.strong.get(f"H{n.group()}") if n else None


def verse_map(path):
    """WLC verse -> [KJV verses] where they differ."""
    root = etree.parse(path).getroot()
    out = defaultdict(list)
    for v in root.iter():
        if local(v.tag) == "verse" and v.get("wlc"):
            out[v.get("wlc")].append(v.get("kjv"))
    return out


def read_bsb(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["Book"], r["Chapter"], r["Verse"])] = r["Text"].strip()
    return out


def read_book(path):
    """[(chapter, verse, text, [token dicts], para_after)]"""
    root = etree.parse(path).getroot()
    verses = []
    for v in root.iter(OSIS + "verse"):
        _, c, n = v.get("osisID").split(".")
        text, tokens, space, para = "", [], False, False

        def add_word(w, bracket=None):
            nonlocal text, space
            raw = "".join(w.itertext())
            if space:
                text += " "
            if bracket:
                text += bracket
            start = len(text)
            parts = raw.split("/")
            disp = "".join(parts)
            text += disp
            tokens.append(dict(start=start, end=len(text), form=disp, parts=parts,
                               lemma=w.get("lemma") or "", morph=w.get("morph") or "",
                               ketiv=w.get("type") == "x-ketiv"))
            space = True

        for el in v:
            name = local(el.tag)
            if name == "w":
                add_word(el)
            elif name == "seg":
                t = el.get("type")
                if t == "x-maqqef":
                    text += "־"
                    space = False
                elif t == "x-sof-pasuq":
                    text += "׃"
                elif t == "x-paseq":
                    text += " ׀"
                elif t in ("x-pe", "x-samekh"):
                    para = True
            elif name == "note" and el.get("type") == "variant":
                qs = [w for r in el.iter(OSIS + "rdg") if r.get("type") == "x-qere" for w in r.iter(OSIS + "w")]
                for k, w in enumerate(qs):
                    add_word(w, "[" if k == 0 else None)
                if qs:
                    text += "]"
        verses.append((c, n, text, tokens, para))
    return verses


def add_tokens(db, lex, sid, text, tokens, stats):
    for idx, t in enumerate(tokens):
        lang, segs = hebrew.segments(t["morph"])
        lemmas = [l for l in t["lemma"].split("/")]
        # lemmas go to the morphemes that aren't suffixes, in order
        seg_lemmas, li = [], 0
        for s in segs:
            if s[:1] == "S" or li >= len(lemmas):
                seg_lemmas.append(None)
            else:
                seg_lemmas.append(lemmas[li])
                li += 1
        main = hebrew.main_index(segs)
        ml = seg_lemmas[main] if main < len(seg_lemmas) else None
        head = lex.headword(ml) if ml else None
        tid = db.execute(
            'INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, idx, u16(text, t["start"]), u16(text, t["end"]), t["form"],
             head or (ml and re.sub(r"\s", "", ml)), hebrew.lemma_key(ml) if ml else None,
             hebrew.agdt(segs[main]) if segs else None, "oshb")).lastrowid
        for rank, s in enumerate(segs):
            l = seg_lemmas[rank] if rank < len(seg_lemmas) else None
            form = t["parts"][rank] if rank < len(t["parts"]) else ""
            db.execute("INSERT INTO morph VALUES (?,?,?,?,?,?)",
                       (tid, rank, form, (lex.headword(l) or re.sub(r"\s", "", l)) if l else None,
                        hebrew.lemma_key(l) if l else None, hebrew.describe(s, lang)))
        stats["tokens"] += 1
        stats["lemma"] += 1 if ml else 0
        stats["headword"] += 1 if head else 0


def build(sources, out):
    db = sqlite3.connect(out)
    wlc = os.path.join(sources, "morphhb", "wlc")
    lex = Lexicon(os.path.join(sources, "HebrewLexicon"))
    vmap = verse_map(os.path.join(wlc, "VerseMap.xml"))
    bsb = read_bsb(os.path.join(sources, "bible_databases", "formats", "csv", "BSB.csv"))
    ot = {row[0]: row for row in OT}
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report, pairs = {}, []
    for k, (osis, title, csvname, section) in enumerate(BOOKS):
        verses = read_book(os.path.join(wlc, f"{osis}.xml"))
        wid = db.execute(
            "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
            "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start + k, f"urn:hbo:wlc.{osis}", section, title, "prose", "bible", f"urn:hbo:wlc.{osis}.oshb",
             "", "Berean Standard Bible", "complete", "oshb", "hbo", CREDIT)).lastrowid
        stats = Counter()
        # English: each Hebrew verse's KJV-numbered verses (explicit map first)
        claimed = {kv for wv, kvs in vmap.items() if wv.startswith(osis + ".") for kv in kvs}
        # group verses into blocks: a verse with no English of its own (a psalm's
        # title, which English Bibles fold into verse 1) joins the verse that
        # shares its English verse
        groups = []
        for v in verses:
            key = f"{osis}.{v[0]}.{v[1]}"
            targets = vmap.get(key) or ([key] if key not in claimed else [])
            if groups and (not groups[-1]["targets"] or set(targets) & set(groups[-1]["targets"])) \
                    and groups[-1]["verses"][-1][0] == v[0]:
                groups[-1]["verses"].append(v)
                groups[-1]["targets"] += [t for t in targets if t not in groups[-1]["targets"]]
            else:
                groups.append(dict(verses=[v], targets=list(targets)))
        blocks = []
        prev_chapter, para_next, seq = None, True, 0
        for bi, g in enumerate(groups):
            english = " ".join(bsb.get((csvname, *t.split(".")[1:]), "") for t in g["targets"]).strip()
            if not english:
                stats["no_english"] += 1
            first, last = g["verses"][0], g["verses"][-1]
            cs, ce = f"{first[0]}.{first[1]}", f"{last[0]}.{last[1]}"
            bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                             " VALUES (?,?,?,?,?,?)", (wid, bi, cs, ce, english, "[]")).lastrowid
            blocks.append((bid, cs, english))
            for c, n, text, tokens, para_after in g["verses"]:
                heading = None
                if c != prev_chapter:
                    heading = f"Psalm {c}" if osis == "Ps" else f"Chapter {c}"
                para = c != prev_chapter or para_next
                prev_chapter, para_next = c, para_after
                cite = f"{c}.{n}"
                sid = db.execute(
                    "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,"
                    "markers) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (wid, bid, seq, cite, None, None, heading, None, 1 if para else 0, text,
                     json.dumps([[0, "section", n]]))).lastrowid
                seq += 1
                add_tokens(db, lex, sid, text, tokens, stats)
        # parallels: through the English, as for the Vulgate
        row = ot.get(csvname)
        if row:
            _, vtitle, _, greek = row
            A = [(cite, eng) for _, cite, eng in blocks]
            ids = [bid for bid, _, _ in blocks]
            for language, others in (("lat", [(vtitle, None)]), ("grc", greek)):
                B = []
                for otitle, chapters in others:
                    B.extend(work_verses(db, otitle, chapters, language))
                if osis in ("Ezra", "Neh") and language == "grc":
                    B = [b for b in B if b]         # (2 Esdras' chapter range is in OT)
                owner = align_verses(A, [(b[1], b[2]) for b in B])
                for i, js in enumerate(owner):
                    if not A[i][1]:
                        continue
                    for j in js:
                        pairs.append((ids[i], B[j][0]))
                stats[f"paired_{language}"] = sum(1 for o in owner if o)
        report[title] = dict(verses=len(verses), blocks=len(blocks), **stats)
    db.execute("CREATE TABLE IF NOT EXISTS parallel (block_id INT, other_block_id INT)")
    db.executemany("INSERT INTO parallel VALUES (?,?)", pairs + [(b, a) for a, b in pairs])
    db.execute("CREATE INDEX IF NOT EXISTS parallel_block ON parallel(block_id)")
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


def work_verses(db, title, chapters, language):
    """[(block id, cite, english)] of a Latin or Greek work."""
    row = db.execute("SELECT id FROM work WHERE title = ? AND COALESCE(language, 'grc') = ?",
                     (title, language)).fetchone()
    if not row:
        return []
    out = []
    for bid, cite, english in db.execute("SELECT id, cite_start, english FROM block WHERE work_id = ? ORDER BY seq",
                                         (row[0],)):
        if chapters:
            c = int(re.match(r"\d+", cite).group())
            if not chapters[0] <= c <= chapters[1]:
                continue
        out.append((bid, cite, english or ""))
    return out


if __name__ == "__main__":
    build(*sys.argv[1:3])
