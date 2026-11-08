"""Add Coptic texts from Marcion (Nag Hammadi Library, Berlin Codex 8502) to texts.db.

Usage: python build_marcion.py <texts.db> <NagHammadi.msql.bz2> [CodexAkhmim.msql.bz2 …]

The texts are shown line by line as in the codices and cited by codex page and
line ("17.4"); each page is a part of the work. A word broken across two lines
becomes two tokens with the same analysis, so either half can be tapped.

The analysis of each bound group (its morphemes, with lemma and part of
speech) comes from the Coptic SCRIPTORIUM NLP tools, run once and cached in
data/coptic_nlp/ (see coptic_nlp_cache.py). Those tools are trained on
Sahidic, so for texts in other dialects (Lycopolitan: NHC I, X, XI) the
analysis is rougher. The Gospel of Thomas is skipped here because Coptic
SCRIPTORIUM's own edition (build_coptic.py) is used instead.
"""
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter

import coptic
import coptic_nlp_cache
import marcion

ROMAN = {r: i for i, r in enumerate("I II III IV V VI VII VIII IX X XI XII XIII".split(), 1)}
SKIP = re.compile(r"fragments|Gospel of Thomas", re.I)
CREDIT = ("Coptic text from Marcion by Milan Konvička (GPL v2). Lemmas and parts of speech "
          "assigned automatically with the Coptic SCRIPTORIUM NLP tools (Apache 2.0); "
          "they are trained on Sahidic and less reliable for other dialects.")
COLLECTIONS = {
    "Nag Hammadi Library": dict(author=lambda codex: f"Nag Hammadi Codex {codex}", urn="nhc"),
    "Codex Akhmim": dict(author=lambda codex: "Berlin Codex (BG 8502)", urn="bg8502"),
}


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def is_mark(ch):
    return unicodedata.combining(ch) or "︠" <= ch <= "︯"


def align(groups, letters):
    """Map each analysed group onto the letters of the edition.
    -> [(group, [letter indices])]; groups that cannot be placed are dropped."""
    out, p, lost = [], 0, 0
    for g in groups:
        want = [ch for ch in unicodedata.normalize("NFD", g[0]) if marcion.is_letter(ch)]
        if not want:
            continue
        n = len(want)
        if letters[p:p + n] != want:
            # resynchronise within a short window
            for skip in range(1, 40):
                if letters[p + skip:p + skip + n] == want:
                    p += skip
                    break
            else:
                lost += 1
                continue
        out.append((g, list(range(p, p + n))))
        p += n
    return out, lost


def main_morph(morphs):
    for tag in coptic.CONTENT:
        for i, m in enumerate(morphs):
            if m[3] == tag:
                return i
    return len(morphs) - 1


def build_book(db, wid, lines, groups):
    text, where, _ = coptic_nlp_cache.prepare(lines)
    letters = [ch for ch in text if marcion.is_letter(ch)]
    assert len(letters) == len(where)
    placed, lost = align(groups, letters)

    # tokens per line: (line index) -> [(start, end, group, form, word id)]
    per_line = {}
    for gi, (g, idx) in enumerate(placed):
        by_line = {}
        for i in idx:
            li, off = where[i]
            by_line.setdefault(li, []).append(off)
        pieces = []
        for li, offs in sorted(by_line.items()):
            line = lines[li]["text"]
            a, b = min(offs), max(offs) + 1
            while b < len(line) and is_mark(line[b]):
                b += 1
            pieces.append((li, a, b))
        form = re.sub(r"\[±?\d*|[\]⟨⟩.]", "", "".join(lines[li]["text"][a:b] for li, a, b in pieces))
        form = re.sub(r"\s+", " ", form).strip()
        # a word broken across lines: its pieces share an id, so the app can
        # highlight both halves
        word = wid * 1_000_000 + gi if len(pieces) > 1 else None
        for li, a, b in pieces:
            per_line.setdefault(li, []).append((a, b, g, form, word))

    stats = Counter(lost=lost, groups=len(placed))
    pages = {}
    for li, ln in enumerate(lines):
        pages.setdefault(ln["page"], []).append(li)
    pending = []
    seq = 0
    for bseq, (page, lis) in enumerate(sorted(pages.items())):
        shown = [li for li in lis if lines[li]["text"]]
        if not shown:
            pending += [n for li in lis for n in lines[li]["notes"]]
            continue
        first, last = lines[shown[0]], lines[shown[-1]]
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)",
                         (wid, bseq, f"{page}.{first['line']}", f"{page}.{last['line']}", "", "[]")).lastrowid
        for li in lis:
            ln = lines[li]
            pending += ln["notes"]
            if not ln["text"]:
                continue
            heading = "; ".join(pending) or None
            pending = []
            cite = f"{page}.{ln['line']}"
            sid = db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, cite, ln["line"], None, heading, None, 0, ln["text"], "[]")).lastrowid
            seq += 1
            stats["lines"] += 1
            for idx, (a, b, g, form, word) in enumerate(sorted(per_line.get(li, []), key=lambda t: t[0])):
                morphs = [m for m in g[1] if m[3] != "PUNCT"]
                if not morphs:
                    continue
                main = morphs[main_morph(morphs)]
                tid = db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source,'
                                 "word_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (sid, idx, u16(ln["text"], a), u16(ln["text"], b), form, main[2],
                                  coptic.key(main[2]), main[3], "coptic-nlp", word)).lastrowid
                for rank, (orig, _norm, lemma, pos) in enumerate(morphs):
                    db.execute("INSERT INTO morph VALUES (?,?,?,?,?,?)",
                               (tid, rank, orig, lemma, coptic.key(lemma), pos))
                stats["tokens"] += 1
                stats["split_pieces"] += word is not None
    return stats


def main(out, *dumps):
    db = sqlite3.connect(out)
    report = {}
    works = []      # (codex order key, values) so that codices sort in order
    for dump in dumps:
        coll, books, rows = marcion.read_dump(dump)
        spec = COLLECTIONS[coll["name"]]
        cache = coptic_nlp_cache.load(coll["name"])
        fmt = coll.get("format", "2")
        per_codex = Counter()
        for book, (name, order) in sorted(books.items(), key=lambda kv: kv[1][1]):
            codex, title = marcion.book_title(name)
            per_codex[codex] += 1
            if SKIP.search(name):
                continue
            lines = marcion.book_lines(rows, book, fmt)
            text, _, detok = coptic_nlp_cache.prepare(lines)
            entry = cache.get(str(book))
            sha = coptic_nlp_cache.input_sha(text, detok)
            if not entry or entry["input_sha"] != sha:
                print(f"warning: no current analysis for {name}; run coptic_nlp_cache.py", file=sys.stderr)
                entry = dict(groups=[])
            author = spec["author"](codex)
            urn = f"urn:cts:copticLit:{spec['urn']}" + (f".{ROMAN.get(codex, codex)}" if codex else "") \
                  + f".{per_codex[codex]}"
            works.append((author, urn, title, lines, entry["groups"], name))

    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    for i, (author, urn, title, lines, groups, name) in enumerate(works):
        wid = db.execute(
            "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,"
            "parse_source,language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start + i, urn, author, title, "verse", "codex", urn, "", "", "complete",
             "coptic-nlp", "cop", CREDIT)).lastrowid
        report[name] = build_book(db, wid, lines, groups)

    # the Gospel of Thomas (Coptic SCRIPTORIUM) belongs after the Apocryphon of John in Codex II
    thomas = db.execute("SELECT id FROM work WHERE urn = 'urn:cts:copticLit:nh.thomas'").fetchone()
    john = db.execute("SELECT sort FROM work WHERE urn = 'urn:cts:copticLit:nhc.2.1'").fetchone()
    if thomas and john:
        db.execute("UPDATE work SET sort = sort + 1 WHERE sort > ?", john)
        db.execute("UPDATE work SET sort = ? WHERE id = ?", (john[0] + 1, thomas[0]))

    db.commit()
    db.execute("VACUUM")
    db.close()
    total = Counter()
    for s in report.values():
        total.update(s)
    report["total"] = dict(total)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
