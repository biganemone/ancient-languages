"""The Bhagavad Gītā: the Digital Corpus of Sanskrit's text and analyses
(Oliver Hellwig, CC BY 4.0; the critical edition's text of Mahābhārata
6.23–40), verse-numbered, with Annie Besant's translation (1922, public
domain) as English.

  python build_sanskrit.py <sources> <texts.db>

- DCS gives sentences, not verses. Verse and half-verse boundaries come from
  aligning its text, letter by letter, with a verse-numbered edition
  (gita/gita's verse.json, the Unlicense; Devanāgarī, transliterated here).
- A handful of DCS sentences (1.1, the opening of chapter 2) are stored as
  separate words only, without their sandhi groups; those groups are taken
  from the numbered edition's spelling.
- Each sandhi group is split into the words a printed IAST text separates
  (sanskrit.split_group). Each piece is a token; its words are morph rows
  ("the parts of this word"), with readable parses.
- One block per verse; a verse's half-lines (and any "X uvāca" line) are
  lines of one segment, separated by U+2028.
- Chapter 13: the critical edition has no "arjuna uvāca: prakṛtiṃ puruṣaṃ
  caiva…" verse, so its verses are 13.1–34 (Besant numbers that extra verse
  13.1; her 13.2 is our 13.1).
"""
import bisect
import difflib
import glob
import gzip
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

import sanskrit as S

HERE = os.path.dirname(os.path.abspath(__file__))
CREDIT = ("Sanskrit: the Digital Corpus of Sanskrit (Oliver Hellwig), text and analyses, CC BY 4.0; "
          "verse numbers from the gita/gita dataset. English: Annie Besant, The Bhagavad-Gita (4th ed., 1922), "
          "public domain, from Wikisource.")
LS = " "
# Critical-edition verse counts (Besant's chapter 13 has 35)
VERSES = [47, 72, 43, 42, 29, 47, 30, 28, 34, 42, 55, 20, 34, 27, 20, 24, 28, 78]


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def numbered_edition(path):
    """{chapter: [(verse, [line text…])]} in IAST; a line ends at a daṇḍa or
    after "X uvāca"."""
    out = defaultdict(list)
    for v in json.load(open(path, encoding="utf-8")):
        ch, n = v["chapter_number"], v["verse_number"]
        t = S.deva_to_iast(v["text"])
        t = re.sub(r"\|\|\s*[\d.]+\s*\|\|", "", t)
        t = re.sub(r"((?:dhṛtarāṣṭra|sañjaya|saṃjaya|arjuna|śrī ?bhagavān) ?uvāca)\s*", "\\1\n", t)  # a speaker's line
        lines = []
        for part in re.split(r"\n+|\|", t):
            part = " ".join(part.split())
            if part:
                lines.append(part)
        out[ch].append((n, lines))
    for ch in out:
        out[ch].sort()
    return out


def chapter_files(dcs):
    files = {}
    for f in glob.glob(os.path.join(dcs, "dcs", "data", "conllu", "files", "*", "*BhaG*.conllu")):
        m = re.search(r"BhaG\S* (\d+)-\d+\.conllu$", unicodedata.normalize("NFC", f))
        if m:
            files[int(m.group(1))] = f
    return files


class Aligner:
    """Maps positions in one letter string to another (difflib opcodes)."""

    def __init__(self, a, b):
        self.ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        self.starts = [op[1] for op in self.ops]
        # edition letters DCS has nothing at all for (not variant readings, which are "replace")
        self.missing = bytearray(len(b))
        for tag, a1, a2, b1, b2 in self.ops:
            if tag == "insert":
                self.missing[b1:b2] = b"\x01" * (b2 - b1)

    def __call__(self, i):
        k = max(0, bisect.bisect_right(self.starts, i) - 1)
        tag, a1, a2, b1, b2 = self.ops[k]
        if tag == "equal":
            return b1 + (i - a1)
        return b1


def chapter(sents, edition):
    """-> [(verse number, [line: [group]])]; a group is {form, words}.
    `edition` is [(number or cite, [line text…])]. Words the edition has and
    DCS lacks entirely (2.21's first half-line, some "X uvāca" lines) are
    added from the edition, unanalysed; where the two read differently, DCS's
    reading is kept."""
    ed, line_at, ed_groups = "", [], []
    for vi, (n, lines) in enumerate(edition):
        for li, line in enumerate(lines):
            line_at.append((len(ed), vi, li))
            for g in line.split():
                ed_groups.append((len(ed), len(ed) + len(S.letters(g)), S.nfc(g)))
                ed += S.letters(g)
    dc, items = "", []
    for s in sents:
        plain = not any(len(g["words"]) > 1 for g in s["groups"]) and \
            any("Annotator" in w["misc"] for g in s["groups"] for w in g["words"])
        for g in s["groups"]:
            items.append((len(dc), len(dc) + len(S.letters(g["form"])), g, plain))
            dc += S.letters(g["form"])
    to_ed = Aligner(dc, ed)
    line_starts = [p for p, _, _ in line_at]
    group_starts = [p for p, _, _ in ed_groups]
    placed = defaultdict(list)        # (verse index, line index) -> [(edition position, order, group)]
    order = 0

    def put(p, g):
        nonlocal order
        li = max(0, bisect.bisect_right(line_starts, p) - 1)
        _, vi, lj = line_at[li]
        placed[(vi, lj)].append((p, order, g))
        order += 1

    used = set()                      # edition groups that DCS material landed in
    pending = []                      # an unsandhied sentence's words, regrouped by the edition's groups

    def flush():
        by, seen = defaultdict(list), []
        for p, g in pending:
            k = max(0, bisect.bisect_right(group_starts, p) - 1)
            if k not in by:
                seen.append(k)
            by[k].extend(g["words"])
        for k in seen:
            for w in by[k]:
                w["misc"].setdefault("Unsandhied", w["form"])
            used.add(k)
            put(ed_groups[k][0], {"form": ed_groups[k][2], "words": by[k]})
        pending.clear()

    for a, b, g, plain in items:
        p = to_ed(a)
        if plain:
            pending.append((p, g))
            continue
        flush()
        k = max(0, bisect.bisect_right(group_starts, p) - 1)
        used.update(range(k, max(k, bisect.bisect_left(group_starts, to_ed(max(a, b - 1)) + 1))))
        put(p, g)
    flush()
    for k, (p, q, form) in enumerate(ed_groups):
        if k in used or q - p < 2:
            continue
        if sum(to_ed.missing[p:q]) >= (q - p) * 0.7:
            put(p, {"form": form, "words": []})
    out = []
    for vi, (n, lines) in enumerate(edition):
        vlines = []
        for lj in range(len(lines)):
            gs = sorted(placed.get((vi, lj), []), key=lambda x: (x[0], x[1]))
            if gs:
                vlines.append([g for _, _, g in gs])
        out.append((n, vlines))
    return out


def besant(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {int(c): {int(n): t for n, t in vs.items()} for c, vs in json.load(f).items()}


def add_unit(db, wid, bseq, seq, cite, label, lines, english, heading, cstats, lemma_ids):
    """One verse or section: a block with its English, and one segment whose
    lines (half-verses) are joined by U+2028; each sandhi piece a token, its
    words morph rows."""
    bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                     " VALUES (?,?,?,?,?,?)", (wid, bseq, cite, cite, english, "[]")).lastrowid
    text, toks = "", []
    for li, line in enumerate(lines):
        if li:
            text += LS
        first = True
        for g in line:
            for piece, idx in S.split_group(g["form"], g["words"]):
                if not first:
                    text += " "
                first = False
                toks.append((len(text), len(text) + len(piece), piece, [g["words"][i] for i in idx]))
                text += piece
    sid = db.execute(
        "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,"
        "markers) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (wid, bid, seq, cite, None, None, heading, None, 1, text, json.dumps([[0, "section", label]]))).lastrowid
    for idx, (a, b, piece, words) in enumerate(toks):
        if not words:                    # in the text, but not analysed in DCS
            db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                       " VALUES (?,?,?,?,?,NULL,NULL,NULL,?)",
                       (sid, idx, u16(text, a), u16(text, b), piece, "dcs"))
            cstats["unanalysed"] += 1
            continue
        m = S.main_word(words)
        head = words[m]
        tid = db.execute(
            'INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, idx, u16(text, a), u16(text, b), piece, head["lemma"], S.lemma_key(head["lemma"]),
             S.agdt(head), "dcs")).lastrowid
        for rank, w in enumerate(words):
            if w["misc"].get("LemmaId"):
                lemma_ids[(S.lemma_key(w["lemma"]), w["misc"]["LemmaId"])] += 1
            db.execute("INSERT INTO morph VALUES (?,?,?,?,?,?)",
                       (tid, rank, S.nfc(w["misc"].get("Unsandhied") or w["form"]), w["lemma"],
                        S.lemma_key(w["lemma"]), S.describe(w)))
        cstats["tokens"] += 1
        cstats["words"] += len(words)
        cstats["multiword"] += 1 if len(words) > 1 else 0
    if not english:
        cstats["no_english"] += 1


def save_lemma_ids(db, lemma_ids):
    db.execute("CREATE TABLE IF NOT EXISTS san_lemma (lemma_key TEXT, lemma_id TEXT, n INT)")
    db.executemany("INSERT INTO san_lemma VALUES (?,?,?)", [(k, i, n) for (k, i), n in lemma_ids.items()])


def build(sources, out):
    db = sqlite3.connect(out)
    dcs = os.path.join(sources, "dcs")
    edition = numbered_edition(os.path.join(sources, "gita", "data", "verse.json"))
    english = besant(os.path.join(HERE, "data", "besant_gita.json.gz"))
    files = chapter_files(dcs)
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (start, "urn:san:dcs.bhagavadgita", "Mahābhārata", "Bhagavad Gītā", "prose", "chapters",
         "urn:san:dcs.bhagavadgita.dcs", "", "Annie Besant (1922)", "complete", "dcs", "san", CREDIT)).lastrowid
    stats, report = Counter(), {}
    lemma_ids = Counter()            # (lemma key, DCS lemma id): which homonym the text means, for glosses
    seq = bseq = 0
    for ch in range(1, 19):
        sents = S.read_conllu(files[ch])
        verses = chapter(sents, edition[ch])
        cstats = Counter()
        for n, lines in verses:
            cite_n = n
            if not any(g["words"] for line in lines for g in line):
                lines = []                       # (13.1 of the vulgate: not in the critical edition)
            if ch == 13:
                if n == 1 and not lines:
                    continue
                cite_n = n - 1
            if not lines:
                cstats["empty_verses"] += 1
                continue
            eng_n = cite_n + 1 if ch == 13 else cite_n
            eng = english.get(ch, {}).get(eng_n, "")
            cite = f"{ch}.{cite_n}"
            heading = f"Chapter {ch}" if cite_n == 1 else None
            add_unit(db, wid, bseq, seq, cite, str(cite_n), lines, eng, heading, cstats, lemma_ids)
            bseq += 1
            seq += 1
            cstats["verses"] += 1
        report[f"chapter {ch}"] = dict(cstats, expected=VERSES[ch - 1])
        stats.update(cstats)
    report["total"] = dict(stats)
    save_lemma_ids(db, lemma_ids)
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    build(*sys.argv[1:3])
