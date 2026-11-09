"""Add the Gospel of Nicodemus to texts.db: the Acts of Pilate (Greek A) and
the Descent into Hell (Greek), Tischendorf's text (1876), transcribed for this
project (data/acts_of_pilate_tischendorf.txt), with Alexander Walker's English
(Ante-Nicene Fathers 8, 1886, from Wikisource: data/walker_acts_of_pilate.json).

Usage: python build_apocrypha.py <texts.db> <treebank dir> [macula tsv]

One work (author "New Testament Apocrypha", form "chapters"), cited
chapter.section as Tischendorf numbers them ("0" = the prologue, 17-27 = the
Descent, his "Caput I. (XVII.)" etc.). A block per chapter carries Walker's
English for that chapter; a segment per section. Parsed with Morpheus, ranked
by NT usage like the Septuagint (build_lxx.py), with NT forms for names.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter

import greek
import morpheus
from build_lxx import koine_variants, nt_frequency, NT_FORMS
from build_texts import lemma_frequency, tokens_for

HERE = os.path.dirname(os.path.abspath(__file__))
GREEK = os.path.join(HERE, "data", "acts_of_pilate_tischendorf.txt")
ENGLISH = os.path.join(HERE, "data", "walker_acts_of_pilate.json")
URN = "urn:cts:greekLit:apocrypha.acta_pilati"
CREDIT = ("Tischendorf, Evangelia Apocrypha (2nd ed., 1876), transcribed for this app from the "
          "archive.org scan; English: Alexander Walker (Ante-Nicene Fathers 8, 1886), from Wikisource. "
          "Public domain.")


def read_greek(path=GREEK):
    """-> [(chapter, section, text)] in order, sections joined across pages."""
    out, chapter, section, buf = [], None, None, []

    def flush():
        if chapter is not None and buf:
            text = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if text:
                out.append((chapter, section, text))
        buf.clear()

    pending = ""            # a word broken at the end of a page ("ἐπέ-")
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("# ") or line == "#":
            continue
        if line.startswith("#C "):
            flush()
            chapter, section = int(line.split()[1]), 1
            continue
        if line.startswith("#V "):
            flush()
            section = int(line.split()[1])
            continue
        if line.startswith("#"):        # #P page, #T title, #S separator
            continue
        line = line.strip()
        if not line:
            continue
        if pending:
            line = pending + line
            pending = ""
        if line.endswith("-"):
            words = line[:-1].rsplit(" ", 1)
            pending = words[-1]
            line = words[0] if len(words) > 1 else ""
        buf.append(line)
    flush()
    return out


def read_english(path=ENGLISH):
    """{chapter: English text}: Walker's paragraphs, without the titles and headings."""
    data = json.load(open(path, encoding="utf-8"))
    out = {}
    for n, paras in data.items():
        keep = []
        for p in paras:
            if re.match(r"^(The Gospel of Nicodemus\.|Part I+\.|First Greek Form\.|Greek Form\.|—+|"
                        r"Memorials of Our Lord|Chapter \d+)", p):
                continue
            keep.append(re.sub(r"^Prologue\.—", "", p))
        out[int(n)] = "\n\n".join(keep)
    return out


def build(db, sort, frequency):
    sections = read_greek()
    english = read_english()
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, URN, "New Testament Apocrypha", "Gospel of Nicodemus", "prose", "chapters", URN + ".tischendorf",
         "", "Alexander Walker", "Acts of Pilate and Descent into Hell", "morpheus", "grc", CREDIT)).lastrowid
    tokens, blocks = [], {}
    for seq, (c, v, text) in enumerate(sections):
        new_chapter = c not in blocks
        if new_chapter:
            blocks[c] = db.execute(
                "INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers) VALUES (?,?,?,?,?,?)",
                (wid, len(blocks), f"{c}.{v}", f"{c}.{v}", english.get(c, ""), "[]")).lastrowid
        db.execute("UPDATE block SET cite_end = ? WHERE id = ?", (f"{c}.{v}", blocks[c]))
        heading = None
        if new_chapter:
            heading = ("Prologue" if c == 0 else
                       "Part II · The Descent into Hell · Chapter 17" if c == 17 else f"Chapter {c}")
        sid = db.execute(
            "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (wid, blocks[c], seq, f"{c}.{v}", None, None, heading, None, 1, text,
             json.dumps([[0, "section", str(v)]]))).lastrowid
        for t in tokens_for(text, 0):
            t["seg"] = sid
            tokens.append(t)

    need = sorted({t["form"] for t in tokens})
    analyses = morpheus.analyses(need, "attic", frequency)
    missing = [f for f in need if not analyses.get(f)]
    variants = {f: koine_variants(f) for f in missing}
    extra = morpheus.analyses(sorted({x for vs in variants.values() for x in vs}), "attic", frequency) \
        if any(variants.values()) else {}
    for f, vs in variants.items():
        for x in vs:
            if extra.get(x):
                analyses[f] = extra[x]
                break
    stats = Counter()
    for t in tokens:
        found = analyses.get(t["form"]) or []
        lemma = found[0][0] if found else NT_FORMS.get(greek.bare(t["form"]))
        if found:
            stats["morpheus"] += 1
        elif lemma:
            stats["nt_form"] += 1
        elif t["form"][:1].isupper():
            lemma = t["form"]
            stats["name"] += 1
        else:
            stats["no_parse"] += 1
        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (t["seg"], t["idx"], t["start"], t["end"], t["form"], lemma,
                    greek.lex_key(re.sub(r"\d+$", "", lemma)) if lemma else None, None,
                    "morpheus" if found else None))
    for form, rows in analyses.items():
        for rank, (lemma, parse) in enumerate(rows):
            db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)", (form, rank, lemma, greek.lex_key(lemma), parse))
    return dict(sections=len(sections), chapters=len(blocks), tokens=len(tokens),
                with_english=sum(1 for c in blocks if english.get(c)), **stats)


def main(out, tbdir, macula_tsv=None):
    db = sqlite3.connect(out)
    cols = [r[1] for r in db.execute("PRAGMA table_info(work)")]
    for col in ("language", "credit"):
        if col not in cols:
            db.execute(f"ALTER TABLE work ADD COLUMN {col} TEXT")
    frequency = Counter(lemma_frequency(tbdir))
    frequency.update(nt_frequency(macula_tsv))
    sort = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report = {"Gospel of Nicodemus": build(db, sort, frequency)}
    db.execute("DELETE FROM analysis WHERE rowid NOT IN (SELECT MIN(rowid) FROM analysis GROUP BY form, rank)")
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
