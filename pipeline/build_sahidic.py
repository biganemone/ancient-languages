"""The Sahidic Coptic New Testament: "Sahidic Bible 2" (CrossWire CopSahBible2,
CC BY-SA; the INTF's transcriptions of the principal manuscripts: M569 for
Matthew, P.Palau Ribes 181–183 for Mark, Luke and John, BL Or. 7594 for Acts,
Chester Beatty Coptic A for Paul, M572 for the Catholic Epistles, BL Or. 6803
for Revelation), with the verses it lacks (Jude, ~30 others) from Horner's
edition (1911–24, public domain), analysed with the Coptic SCRIPTORIUM NLP
tools; the BSB as English; and the Greek NT in parallel (table `parallel`).

  python build_sahidic.py analyse <coptic-nlp checkout> <python with its deps> <CopSahBible2.csv>
      run the NLP tools and refresh data/coptic_nlp/sahidic-bible-2.json.gz
  python build_sahidic.py build <CopSahBible2.csv> <BSB.csv> <texts.db>
      add the 27 books (after build_nt.py), using the cached analyses
"""
import csv
import difflib
import gzip
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

import coptic
import coptic_nlp_cache as nlp

HERE = os.path.dirname(os.path.abspath(__file__))
HORNER = os.path.join(HERE, "data", "horner_sahidic_nt.tsv.gz")
CACHE_NAME = "Sahidic Bible 2"

# CSV book names (as in scrollmapper/bible_databases) -> titles (as our Greek NT)
BOOKS = ["Matthew", "Mark", "Luke", "John", "Acts", "Romans", "I Corinthians", "II Corinthians", "Galatians",
         "Ephesians", "Philippians", "Colossians", "I Thessalonians", "II Thessalonians", "I Timothy",
         "II Timothy", "Titus", "Philemon", "Hebrews", "James", "I Peter", "II Peter", "I John", "II John",
         "III John", "Jude", "Revelation of John"]
WORD = re.compile(r"[Ⲁ-⳿Ϣ-ϯ̀-ͯ︠-︯]+")
STATS = Counter()
CREDIT = ("Coptic: Sahidic Bible 2 (C. Askeland, M. Schulz; INTF Münster), CC BY-SA: the principal manuscripts "
          "(M569, P.Palau Ribes 181–183, BL Or. 7594, Chester Beatty Coptic A, M572, BL Or. 6803); verses they lack "
          "from G. W. Horner's edition (1911–24, public domain; CrossWire module CopSahHorner), whose supralinear "
          "strokes and diaereses are also added to the manuscript text where the letters agree. Analysed "
          "automatically with the Coptic SCRIPTORIUM NLP tools. English: Berean Standard Bible (public domain).")


def title(name):
    t = re.sub(r"^III ", "3 ", re.sub(r"^II ", "2 ", re.sub(r"^I ", "1 ", name)))
    return "Revelation" if t == "Revelation of John" else t


def read_verses(csv_path, strokes=False):
    """{book: [(chapter, verse, text, source)]}: Sahidic Bible 2, Horner where it
    is empty; with strokes=True, Horner's strokes added to the manuscript text
    (the NLP analyses are of the unstroked text, so the cache stays valid)."""
    horner = {}
    with gzip.open(HORNER, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            b, c, v, t = line.rstrip("\n").split("\t", 3)
            horner[(b, c, v)] = t
    out = defaultdict(list)
    seen = set()
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Book"] not in BOOKS:
                continue
            key = (r["Book"], r["Chapter"], r["Verse"])
            seen.add(key)
            text = r["Text"].strip()
            if not text or text == "null" or not coptic.is_coptic(text):
                if key in horner:
                    out[r["Book"]].append((r["Chapter"], r["Verse"], horner[key], "horner"))
                continue
            if strokes and key in horner:
                text, n = add_strokes(text, horner[key])
                STATS["strokes"] += n
            out[r["Book"]].append((r["Chapter"], r["Verse"], text, "sb2"))
    for (b, c, v), t in horner.items():           # verses the CSV doesn't have at all
        if b in BOOKS and (b, c, v) not in seen:
            out[b].append((c, v, t, "horner"))
    for b in out:
        out[b].sort(key=lambda x: (int(x[0]), int(re.match(r"\d+", x[1]).group())))
    return out


STROKE, OVERLINE, DIAERESIS = "\u0304", "\u0305", "\u0308"
HORNER_MARKS = {"\u0305": STROKE, "\u0304": STROKE, "\u0308": DIAERESIS}


def letters(text):
    """[(index, letter, marks)] for each Coptic letter, with the combining marks after it."""
    out = []
    for i, ch in enumerate(text):
        if unicodedata.combining(ch):
            if out:
                out[-1][2].append(ch)
        elif "Ⲁ" <= ch <= "ⳮ" or "Ϣ" <= ch <= "ϯ":
            out.append((i, ch.lower(), []))
    return out


def add_strokes(text, horner):
    """Horner's supralinear strokes and diaereses on the manuscript text:
    letter by letter, wherever the two have the same letters (the transcriptions
    record neither). Letters that already carry a mark (abbreviation bars,
    underdots) are left alone. Returns (text, marks added)."""
    a, b = letters(text), letters(horner)
    insert = {}
    sm = difflib.SequenceMatcher(None, [x[1] for x in a], [x[1] for x in b], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            i, _, own = a[blk.a + k]
            marks = "".join(dict.fromkeys(HORNER_MARKS[m] for m in b[blk.b + k][2] if m in HORNER_MARKS))
            if marks and not own:
                insert[i] = marks
    # strokes on two or more touching letters (a nomen sacrum, or a stroke
    # across two consonants) become one continuous overline; a genitive ⲛ/ⲙ
    # before an abbreviation (ⲛ̄ⲓ︦ⲥ︦) keeps its own stroke
    run = []
    for k, (i, _, _) in enumerate(a + [(-2, "", [])]):
        if STROKE in insert.get(i, "") and (not run or i == run[-1][0] + 1):
            run.append((i, a[k][1]))
            continue
        if len(run) >= 3 and run[0][1] in "ⲛⲙ":
            run = run[1:]
        if len(run) >= 2:
            for j, _ in run:
                insert[j] = insert[j].replace(STROKE, OVERLINE)
        run = [(i, a[k][1])] if i >= 0 and STROKE in insert.get(i, "") else []
    out = "".join(ch + insert.get(i, "") for i, ch in enumerate(text))
    return unicodedata.normalize("NFC", out), len(insert)


def nlp_text(verses):
    """The verses, lacuna marks dropped, separated by a middle dot (the
    pipeline joins words across plain line breaks, as for a word broken at a
    manuscript line end)."""
    return " ·\n".join(re.sub(r"[\[\]〚〛()|$`.]+|…", " ", t) for _, _, t, _ in verses)


def analyse(nlp_dir, python, csv_path):
    verses = read_verses(csv_path)
    cache = nlp.load(CACHE_NAME)
    todo = {}
    for book in BOOKS:
        text = nlp_text(verses[book])
        sha = nlp.input_sha(text, 0)
        if cache.get(book, {}).get("input_sha") != sha:
            todo[book] = (text, sha)
    print(f"{len(todo)} books to analyse", file=sys.stderr)
    for i in range(0, len(todo), 6):
        chunk = dict(list(todo.items())[i:i + 6])
        groups = nlp.run(nlp_dir, python, {b.replace(" ", "_"): t for b, (t, _) in chunk.items()}, 0)
        for book, (_, sha) in chunk.items():
            cache[book] = dict(input_sha=sha, detok=0, groups=groups[book.replace(" ", "_")])
        print("done", list(chunk), file=sys.stderr)
    path = nlp.cache_path(CACHE_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
    print(path, os.path.getsize(path), file=sys.stderr)


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def main_morph(morphs):
    for tag in coptic.CONTENT:
        for i, m in enumerate(morphs):
            if m[3] == tag:
                return i
    return len(morphs) - 1


def build(csv_path, bsb_csv, out):
    db = sqlite3.connect(out)
    verses = read_verses(csv_path, strokes=True)
    cache = nlp.load(CACHE_NAME)
    bsb = defaultdict(dict)
    with open(bsb_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bsb[r["Book"]][(r["Chapter"], r["Verse"])] = r["Text"].strip()
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report, pairs = {}, []
    for n, book in enumerate(BOOKS):
        t = title(book)
        greek = {}
        row = db.execute("SELECT id FROM work WHERE title = ? AND form = 'bible' AND COALESCE(language, 'grc') = 'grc' "
                         "AND author = 'New Testament'", (t,)).fetchone()
        if row:
            greek = {cite: (bid, para) for bid, cite, para in db.execute(
                "SELECT b.id, b.cite_start, (SELECT s.para_start FROM segment s WHERE s.block_id = b.id "
                "ORDER BY s.seq LIMIT 1) FROM block b WHERE b.work_id = ?", (row[0],))}
        wid = db.execute(
            "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
            "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start + n, f"urn:cts:copticLit:nt.sahidic.{n + 1:02d}", "Sahidic New Testament", t, "prose", "bible",
             f"urn:cts:copticLit:nt.sahidic.{n + 1:02d}.sb2", "", "Berean Standard Bible", "complete",
             "coptic-nlp", "cop", CREDIT)).lastrowid
        tokens, prev_chapter = [], None
        bsb_book = bsb.get("Revelation" if book == "Revelation of John" else t, {})
        for seq, (c, v, text, source) in enumerate(verses[book]):
            cite = f"{c}.{v}"
            g = greek.get(cite)
            heading = f"Chapter {c}" if c != prev_chapter else None
            para = c != prev_chapter or bool(g and g[1])
            prev_chapter = c
            bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                             " VALUES (?,?,?,?,?,?)", (wid, seq, cite, cite, bsb_book.get((c, v), ""), "[]")).lastrowid
            markers = [[0, "section", v]]
            sid = db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, cite, None, None, heading, "horner" if source == "horner" else None,
                 1 if para else 0, text, json.dumps(markers))).lastrowid
            for m in WORD.finditer(text):
                if coptic.is_coptic(m.group()):
                    tokens.append(dict(seg=sid, start=u16(text, m.start()), end=u16(text, m.end()), form=m.group()))
            if g:
                pairs.append((bid, g[0]))
        # the analyses, aligned word for word
        groups = [gr for gr in cache.get(book, {}).get("groups", []) if coptic.key(gr[0])]
        a = [coptic.key(x["form"]) for x in tokens]
        b = [coptic.key(gr[0]) for gr in groups]
        matched = 0
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op in ("equal", "replace") and i2 - i1 == j2 - j1:
                for k in range(i2 - i1):
                    tokens[i1 + k]["group"] = groups[j1 + k]
                matched += i2 - i1
        idx = Counter()
        for x in tokens:
            morphs = [m for m in (x.get("group") or [None, []])[1] if m[3] != "PUNCT"]
            main = morphs[main_morph(morphs)] if morphs else None
            tid = db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                             " VALUES (?,?,?,?,?,?,?,?,?)",
                             (x["seg"], idx[x["seg"]], x["start"], x["end"], x["form"],
                              main[2] if main else None, coptic.key(main[2]) if main else None,
                              main[3] if main else None, "coptic-nlp" if main else None)).lastrowid
            idx[x["seg"]] += 1
            for rank, (orig, norm, lemma, pos) in enumerate(morphs):
                db.execute("INSERT INTO morph VALUES (?,?,?,?,?,?)",
                           (tid, rank, norm, lemma, coptic.key(lemma), pos))
        report[t] = dict(verses=len(verses[book]), horner=sum(1 for v in verses[book] if v[3] == "horner"),
                         tokens=len(tokens), analysed=f"{100 * matched / max(1, len(tokens)):.1f}%",
                         greek_pairs=sum(1 for c, v, _, _ in verses[book] if f"{c}.{v}" in greek))
    db.execute("CREATE TABLE IF NOT EXISTS parallel (block_id INT, other_block_id INT)")
    db.executemany("INSERT INTO parallel VALUES (?,?)", pairs + [(g, s) for s, g in pairs])
    db.execute("CREATE INDEX IF NOT EXISTS parallel_block ON parallel(block_id)")
    db.commit()
    report["strokes_added"] = STATS["strokes"]
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "analyse":
        analyse(*sys.argv[2:5])
    else:
        build(*sys.argv[2:5])
