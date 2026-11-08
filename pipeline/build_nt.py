"""Add the Greek New Testament to texts.db: the SBL Greek New Testament
(paragraphs, verses, punctuation) with MACULA Greek's lemmas and morphology,
and the Berean Standard Bible as the English.

Usage: python build_nt.py <SBLGNT repo> <macula-greek repo> <BSB.csv> <texts.db>

Each of the 27 books is a work (author "New Testament", form "bible"), with
a part per chapter. A block is a verse, the smallest unit the Greek and the
English share, so the reader can alternate them verse by verse; the SBLGNT's
paragraphs are kept as paragraph starts, so Greek-only reading flows in
paragraphs. Segments are cited "chapter.verse" ("5.3"; shown as 5:3). The
English for a verse is the BSB's (a verse the SBLGNT omits goes with the one
before, with superscript verse numbers). MACULA's analyses are hand-checked and in context, so the tokens are
stored as source "treebank".

The SBLGNT's apparatus signs (⸀ ⸁ ⸂ ⸃ ⸄ ⸅) are dropped: without the apparatus
they mean nothing to a reader. Its brackets ([ ], ⟦ ⟧) are kept.
"""
import csv
import difflib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict

import greek
from lxml import etree

# (SBLGNT file, MACULA book code, BSB name, title)
BOOKS = [
    ("Matt", "MAT", "Matthew", "Matthew"), ("Mark", "MRK", "Mark", "Mark"),
    ("Luke", "LUK", "Luke", "Luke"), ("John", "JHN", "John", "John"),
    ("Acts", "ACT", "Acts", "Acts"), ("Rom", "ROM", "Romans", "Romans"),
    ("1Cor", "1CO", "I Corinthians", "1 Corinthians"), ("2Cor", "2CO", "II Corinthians", "2 Corinthians"),
    ("Gal", "GAL", "Galatians", "Galatians"), ("Eph", "EPH", "Ephesians", "Ephesians"),
    ("Phil", "PHP", "Philippians", "Philippians"), ("Col", "COL", "Colossians", "Colossians"),
    ("1Thess", "1TH", "I Thessalonians", "1 Thessalonians"),
    ("2Thess", "2TH", "II Thessalonians", "2 Thessalonians"),
    ("1Tim", "1TI", "I Timothy", "1 Timothy"), ("2Tim", "2TI", "II Timothy", "2 Timothy"),
    ("Titus", "TIT", "Titus", "Titus"), ("Phlm", "PHM", "Philemon", "Philemon"),
    ("Heb", "HEB", "Hebrews", "Hebrews"), ("Jas", "JAS", "James", "James"),
    ("1Pet", "1PE", "I Peter", "1 Peter"), ("2Pet", "2PE", "II Peter", "2 Peter"),
    ("1John", "1JN", "I John", "1 John"), ("2John", "2JN", "II John", "2 John"),
    ("3John", "3JN", "III John", "3 John"), ("Jude", "JUD", "Jude", "Jude"),
    ("Rev", "REV", "Revelation of John", "Revelation"),
]
URN = "urn:cts:greekLit:tlg0031.tlg{:03d}"
CREDIT = ("Greek: The SBL Greek New Testament, ed. Michael W. Holmes (Society of Biblical Literature "
          "and Logos Bible Software, 2010), CC BY 4.0. Lemmas and morphology: MACULA Greek Linguistic "
          "Datasets, available at https://github.com/Clear-Bible/macula-greek/ (Biblica), CC BY 4.0. "
          "English: the Berean Standard Bible (public domain).")

SIGLA = re.compile(r"[⸀⸁⸂⸃⸄⸅]\d?")
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

POS = {"noun": "n", "verb": "v", "det": "l", "adj": "a", "adv": "d", "conj": "c", "prep": "r",
       "pron": "p", "ptcl": "g", "num": "m", "intj": "i"}
PERSON = {"first": "1", "second": "2", "third": "3"}
NUMBER = {"singular": "s", "plural": "p"}
TENSE = {"present": "p", "imperfect": "i", "future": "f", "aorist": "a", "perfect": "r", "pluperfect": "l"}
MOOD = {"indicative": "i", "subjunctive": "s", "optative": "o", "imperative": "m", "infinitive": "n",
        "participle": "p"}
VOICE = {"active": "a", "middle": "m", "passive": "p", "middlepassive": "e"}
GENDER = {"masculine": "m", "feminine": "f", "neuter": "n"}
CASE = {"nominative": "n", "genitive": "g", "dative": "d", "accusative": "a", "vocative": "v"}
DEGREE = {"comparative": "c", "superlative": "s"}


def postag(r):
    """MACULA's features -> the 9-character AGDT tag the app reads."""
    return "".join([POS.get(r["class"], "-"), PERSON.get(r["person"], "-"), NUMBER.get(r["number"], "-"),
                    TENSE.get(r["tense"], "-"), MOOD.get(r["mood"], "-"), VOICE.get(r["voice"], "-"),
                    GENDER.get(r["gender"], "-"), CASE.get(r["case"], "-"), DEGREE.get(r["degree"], "-")])


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def read_sblgnt(path):
    """[(paragraph: [(chapter, verse, [(word, start, end)], text)])] — a
    paragraph as a list of verses (pieces of verses at paragraph breaks)."""
    root = etree.parse(path).getroot()
    paragraphs = []
    chapter = verse = None
    for p in root.iter("p"):
        verses = []
        text, words = "", []

        def close():
            nonlocal text, words
            if words:
                verses.append((chapter, verse, words, text.rstrip()))
            text, words = "", []

        pending = ""
        for el in p:
            if el.tag == "verse-number":
                close()
                chapter, verse = el.get("id").split()[-1].split(":")
            elif el.tag == "prefix":
                pending += SIGLA.sub("", el.text or "").strip()
            elif el.tag == "w":
                text += pending
                pending = ""
                start = len(text)
                text += el.text
                words.append((el.text, start, len(text)))
            elif el.tag == "suffix":
                suffix = SIGLA.sub("", el.text or "") or " "
                if text.endswith(" ") and suffix.startswith(" "):
                    suffix = suffix[1:]
                text += suffix
        close()
        if verses:
            paragraphs.append(verses)
    return paragraphs


def read_macula(path):
    by_book = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            by_book[r["ref"].split()[0]].append(r)
    return by_book


def read_bsb(path):
    verses = defaultdict(dict)       # book -> {(chapter, verse): text}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            verses[r["Book"]][(r["Chapter"], r["Verse"])] = r["Text"].strip()
    return verses


def build_book(db, sort, n, book, sblgnt_dir, macula, bsb):
    sbl, code, bsb_name, title = book
    paragraphs = read_sblgnt(f"{sblgnt_dir}/data/sblgnt/xml/{sbl}.xml")
    # a block per verse, the smallest unit the Greek and the English share;
    # the SBLGNT's paragraphs survive as paragraph starts (para_start). A verse
    # broken by a paragraph is one block of two pieces.
    blocks = []
    for para in paragraphs:
        for j, (c, v, words, text) in enumerate(para):
            piece = (c, v, words, text, j == 0)
            if blocks and blocks[-1][0][:2] == (c, v):
                blocks[-1].append(piece)
            else:
                blocks.append([piece])

    # English: each BSB verse goes with its verse, or the verse before it (a
    # verse the SBLGNT omits, e.g. Matt 17:21)
    def vkey(c, v):
        return (int(c), int(re.match(r"\d+", v).group()))
    owner = {vkey(*b[0][:2]): bi for bi, b in enumerate(blocks)}
    english = defaultdict(list)
    last = 0
    for (c, v), text in sorted(bsb[bsb_name].items(), key=lambda kv: vkey(*kv[0])):
        if not text:      # a verse the BSB omits (Rom 16:24)
            continue
        bi = owner.get(vkey(c, v), last)
        last = bi
        english[bi].append((v, text))

    def english_text(verses):
        if len(verses) == 1:
            return verses[0][1]
        # more than one verse here: number them
        return " ".join(f"{v.translate(SUPERSCRIPT)}\u2009{t}" for v, t in verses)

    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, URN.format(n), "New Testament", title, "prose", "bible", URN.format(n) + ".sblgnt",
         "", "Berean Standard Bible", "complete", "treebank", "grc", CREDIT)).lastrowid

    tokens = []
    seen_chapter = set()
    seq = 0
    for bi, b in enumerate(blocks):
        cite = f"{b[0][0]}.{b[0][1]}"
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)",
                         (wid, bi, cite, cite, english_text(english.get(bi, [])) if bi in english else "",
                          "[]")).lastrowid
        for i, (c, v, words, text, para_start) in enumerate(b):
            heading = None
            if c not in seen_chapter:
                seen_chapter.add(c)
                heading = f"Chapter {c}"
            # the second piece of a verse broken by a paragraph has no number again
            marker = [[0, "section", v]] if i == 0 else []
            sid = db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, cite, None, None, heading, None, 1 if para_start else 0, text,
                 json.dumps(marker))).lastrowid
            seq += 1
            for idx, (w, a, e) in enumerate(words):
                tokens.append(dict(seg=sid, idx=idx, start=u16(text, a), end=u16(text, e), form=w, cv=(c, v)))

    # MACULA's words, in order, aligned to the SBLGNT's
    rows = macula[code]
    a = [greek.bare(t["form"]) for t in tokens]
    b = [greek.bare(r["text"]) for r in rows]
    stats = Counter()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal", "replace") and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                tokens[i1 + k]["row"] = rows[j1 + k]
            stats["exact" if op == "equal" else "variant"] += i2 - i1
        else:
            stats["unmatched"] += i2 - i1
    for t in tokens:
        r = t.get("row")
        # οὕτω(ς), ἔξεστι(ν): the dictionaries' headwords have the final letter
        lemma = re.sub(r"\((\w)\)$", r"\1", r["lemma"]) if r else None
        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (t["seg"], t["idx"], t["start"], t["end"], t["form"], lemma,
                    greek.lex_key(lemma) if lemma else None, postag(r) if r else None,
                    "treebank" if r else None))
        if r and r["strong"]:
            db.execute("INSERT OR IGNORE INTO nt_strong VALUES (?,?)", (greek.lex_key(lemma), r["strong"]))
    stats["tokens"] = len(tokens)
    return dict(blocks=len(blocks), english_verses=sum(len(v) for v in english.values()),
                paragraphs=sum(1 for b in blocks for p in b if p[4]), **stats)


def main(sblgnt_dir, macula_dir, bsb_csv, out):
    db = sqlite3.connect(out)
    cols = [r[1] for r in db.execute("PRAGMA table_info(work)")]
    for col in ("language", "credit"):
        if col not in cols:
            db.execute(f"ALTER TABLE work ADD COLUMN {col} TEXT")
    db.execute("CREATE TABLE IF NOT EXISTS nt_strong (lemma_key TEXT PRIMARY KEY, strong TEXT)")
    macula = read_macula(f"{macula_dir}/SBLGNT/tsv/macula-greek-SBLGNT.tsv")
    bsb = read_bsb(bsb_csv)
    report = {}
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    for n, book in enumerate(BOOKS, 1):
        report[book[3]] = build_book(db, start + n - 1, n, book, sblgnt_dir, macula, bsb)
    db.commit()
    total = Counter()
    for r in report.values():
        total.update({k: v for k, v in r.items() if isinstance(v, int)})
    report["total"] = dict(total)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
