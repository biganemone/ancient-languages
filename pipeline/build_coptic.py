"""Add Coptic works from Coptic SCRIPTORIUM (TreeTagger .tt files) to texts.db.

Usage: python build_coptic.py <CopticScriptorium/corpora> <texts.db>

Each saying (or chapter) becomes a prose segment; each bound group (a word as
written, e.g. ⲛ̄ϣⲁϫⲉ = article + noun) becomes a token. Its morphemes, with
their lemmas and part-of-speech tags, go to the `morph` table; the token's own
lemma is the main content morpheme (noun, verb, …), which the reader can
change in the word card.
"""
import json
import re
import sqlite3
import sys
from collections import Counter

import coptic

WORKS = [
    dict(path="thomas-gospel/thomas.gospel_TT/thomas_gospel.tt",
         urn="urn:cts:copticLit:nh.thomas", author="Nag Hammadi Codex II", title="Gospel of Thomas",
         form="sayings", unit="saying",
         credit="Coptic text ed. Paul C. Dilley; annotation by Coptic SCRIPTORIUM "
                "(Dilley, Bremer-McCollum, Schroeder, Zeldes). CC BY 4.0."),
    # two fragments of the Acts of Pilate (Gospel of Nicodemus 9-11) from a White Monastery codex
    dict(path=["acts-pilate/acts.pilate_TT/pilate.1643.27-28.tt", "acts-pilate/acts.pilate_TT/pilate.1643.31-32.tt"],
         urn="urn:cts:copticLit:misc.acts_pilate", author="New Testament Apocrypha",
         title="Acts of Pilate (fragments)", form="chapters", unit="chapter",
         credit="Coptic text after P. Lacau (1904); annotation by Coptic SCRIPTORIUM "
                "(Lydia Bremer-McCollum, Nicholas Wagner). CC BY 4.0."),
]


def paths(work):
    return work["path"] if isinstance(work["path"], list) else [work["path"]]

ATTR = re.compile(r'([\w:]+)="([^"]*)"')


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def read_tt(path):
    """-> list of units: {n, page_breaks: [(group index, page)], groups: [{text, morphs}]}"""
    units, unit, group = [], None, None
    page = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("<pb_xml_id "):
            page = dict(ATTR.findall(line))["pb_xml_id"].split(".")[-1]   # NHAM02.32 -> 32
            if unit is not None:
                unit["page_breaks"].append((len(unit["groups"]), page))
        elif line.startswith("<chapter_n "):
            n = dict(ATTR.findall(line))["chapter_n"]
            if unit is None or unit["n"] != n:
                unit = dict(n=n, page_breaks=[(0, page)] if page else [], groups=[])
                units.append(unit)
        elif line.startswith("<orig_group "):
            group = dict(text=dict(ATTR.findall(line))["orig_group"], morphs=[])
        elif line.startswith("<norm ") and group is not None:
            a = dict(ATTR.findall(line))
            group["morphs"].append(dict(lemma=a.get("lemma", ""), pos=a.get("pos", ""), norm=a.get("norm", "")))
        elif line.startswith("</orig_group") and group is not None:
            if unit is None:
                unit = dict(n="0", page_breaks=[], groups=[])
                units.append(unit)
            unit["groups"].append(group)
            group = None
    return units


def main_morph(morphs):
    for tag in coptic.CONTENT:
        for i, m in enumerate(morphs):
            if m["pos"] == tag:
                return i
    return len(morphs) - 1


def build(db, corpora, work, sort):
    units = []
    for p in paths(work):           # fragments: a chapter split between files is one unit
        for u in read_tt(f"{corpora}/{p}"):
            if units and units[-1]["n"] == u["n"]:
                gap = len(units[-1]["groups"])
                units[-1]["page_breaks"] += [(gap + gi, pg) for gi, pg in u["page_breaks"]]
                units[-1]["groups"] += u["groups"]
            else:
                units.append(u)
    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,language,credit)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, work["urn"], work["author"], work["title"], "prose", work["form"], work["urn"], "", "",
         "complete", "scriptorium", "cop", work["credit"])).lastrowid
    stats = Counter()
    for seq, unit in enumerate(units):
        cite = unit["n"]
        texts, spans = [], []
        pos = 0
        for g in unit["groups"]:
            if texts:
                pos += 1
            spans.append((pos, pos + len(g["text"])))
            texts.append(g["text"])
            pos += len(g["text"])
        text = " ".join(texts)
        label = {"0": "Prol.", "subtitle": "Title"}.get(cite, cite)
        markers = [[0, "section", label]]
        for gi, page in unit["page_breaks"]:
            if gi > 0 and gi < len(spans):
                markers.append([u16(text, spans[gi][0]), "page", page])
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers) VALUES (?,?,?,?,?,?)",
                         (wid, seq, cite, cite, "", "[]")).lastrowid
        heading = {"0": "Prologue", "subtitle": "Title at the end of the text"}.get(cite)
        sid = db.execute(
            "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (wid, bid, seq, cite, None, None, heading, None, 1, text, json.dumps(markers))).lastrowid
        idx = 0
        for g, (a, b) in zip(unit["groups"], spans):
            morphs = [m for m in g["morphs"] if m["pos"] != "PUNCT"]
            if not morphs or not coptic.is_coptic(g["text"]):
                continue
            main = morphs[main_morph(morphs)]
            tid = db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                             " VALUES (?,?,?,?,?,?,?,?,?)",
                             (sid, idx, u16(text, a), u16(text, b), g["text"], main["lemma"],
                              coptic.key(main["lemma"]), main["pos"], "scriptorium")).lastrowid
            for rank, m in enumerate(morphs):
                db.execute("INSERT INTO morph VALUES (?,?,?,?,?,?)",
                           (tid, rank, m["norm"], m["lemma"], coptic.key(m["lemma"]), m["pos"]))
            idx += 1
            stats["tokens"] += 1
            stats["morphs"] += len(morphs)
    return dict(units=len(units), **stats)


def main(corpora, out):
    db = sqlite3.connect(out)
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report = {}
    for i, work in enumerate(WORKS):
        report[work["title"]] = build(db, corpora, work, start + i)
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
