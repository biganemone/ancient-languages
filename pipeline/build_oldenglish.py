"""Old English texts: Beowulf, and the rest of the poetic corpus.

  python build_oldenglish.py <sources> <texts.db>

Beowulf: Klaeber's text (1922) and James M. Garnett's line-for-line
translation (1882), both from the Perseus Digital Library (canonical-angLit,
CC BY-SA). Lemmas and parses come from Klaeber's own glossary, which cites
nearly every word of the poem by line (see oldenglish.py): a hand-made,
in-context analysis. Words the glossary cites only by count ("ond … 311
times") get their lemma from their form.

Blocks are sentences of the poem (ending in . ; ! ?), 2–12 lines, never across
a fitt, each with Garnett's lines of the same numbers.

The other poems: the Anglo-Saxon Poetic Records (Krapp & Dobbie) in Greg
Hidley's electronic text (aspr.py), grouped by manuscript (Junius, Vercelli,
Exeter, the Beowulf manuscript, the Paris Psalter, the Meters of Boethius,
the minor poems). No English yet. Each word gets its possible lemmas and
parses (oe_forms.py: Beowulf's analyses, then Tichý's generated forms of the
Bosworth–Toller headwords), most likely first, like Morpheus's for Greek.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

from lxml import etree

import aspr
import oe_forms
import oe_translations
import oldenglish as oe

TEI = oe.TEI
CAESURA = "  "         # the gap between half-lines
ASPR_CREDIT = ("Text: The Anglo-Saxon Poetic Records, ed. G. P. Krapp and E. V. K. Dobbie (1931–53), in the "
               "electronic text by Greg Hidley (Oxford Text Archive; CC BY-SA 3.0), as published at sacred-texts.com "
               "and collected by the Classical Language Toolkit (cltk/old_english_text_sacred_texts). Lemmas and "
               "parses are automatic: from Beowulf (Klaeber's glossary) and from Ondřej Tichý's Old English "
               "morphological generator (CC BY 4.0) over Bosworth–Toller's headwords.")
CREDIT = ("Text: Fr. Klaeber, Beowulf (1922); translation: James M. Garnett (1882); glossary: Klaeber's, "
          "from which the lemmas and parses are taken. All from the Perseus Digital Library (CC BY-SA). "
          "Bosworth–Toller's Anglo-Saxon Dictionary (1898, 1921; public domain) from the Germanic Lexicon "
          "Project.")


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def line_text(el):
    parts = [el.text or ""]
    for c in el:
        name = c.tag.split("}")[-1] if isinstance(c.tag, str) else ""
        if name == "seg" and c.get("type") == "caesura":
            parts.append(CAESURA)
        else:
            parts.append("".join(c.itertext()))
        parts.append(c.tail or "")
    text = "".join(parts)
    text = re.sub(r"[ \t\n]+", " ", text)
    text = re.sub(r" ?   ?", CAESURA, text)
    return text.replace(" !", "!").replace(" ?", "?").replace(" ;", ";").strip()


def poem(path):
    """[(n, text, fitt heading or None)]"""
    root = etree.parse(path).getroot()
    out = []
    for card in root.iter(TEI + "div"):
        if card.get("subtype") != "card":
            continue
        head = card.find(TEI + "head")
        heading = "".join(head.itertext()).strip() if head is not None else None
        if heading and heading != "Prologue":
            heading = f"Fitt {heading}"
        for k, l in enumerate(card.iter(TEI + "l")):
            out.append((int(l.get("n")), line_text(l), heading if k == 0 else None))
    return out


def translation(path):
    """{line number: text}: Garnett's lines, numbered from each card's start
    and re-synchronised at his own numbers (every fifth line)."""
    root = etree.parse(path).getroot()
    out = {}
    for card in root.iter(TEI + "div"):
        if card.get("subtype") != "card":
            continue
        n = int(card.get("n"))
        for l in card.iter(TEI + "l"):
            if l.get("n") and l.get("n").isdigit() and abs(int(l.get("n")) - n) <= 10:
                n = int(l.get("n"))          # (ignoring misprints: "8025" for 3025)
            text = " ".join("".join(l.itertext()).split())
            if n in out:                     # an extra line in the translation: keep it with the last
                out[n] += " " + text
            else:
                out[n] = text
            n += 1
    return out


def blocks(lines, english):
    out, cur = [], []
    for k, (n, text, heading) in enumerate(lines):
        if heading and cur:
            out.append(cur)
            cur = []
        cur.append((n, text, heading))
        end = re.search(r"[.;!?]['’]?\s*$", text)
        nxt_heading = k + 1 < len(lines) and lines[k + 1][2]
        if (end and len(cur) >= 2) or len(cur) >= 12 or nxt_heading:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [dict(cite_start=str(b[0][0]), cite_end=str(b[-1][0]),
                 english="\n".join(english.get(n, "") for n, _, _ in b).strip(), lines=b) for b in out]


def build_beowulf(db, sources, sort):
    base = f"{sources}/canonical-angLit/data/anon"
    lines = poem(f"{base}/beowulf/anon.beowulf.perseus-ang1.xml")
    english = translation(f"{base}/beowulf/anon.beowulf.perseus-eng1.xml")
    toks = {n: oe.tokenize(text) for n, text, _ in lines}
    words = {oe.form_key(w) for ts in toks.values() for _, _, w in ts}
    glossary = oe.Glossary(f"{base}/klaeber_glossary/anon.klaeber_glossary.perseus-mul1.xml", words)
    analysis = oe.lemmatise({n: [w for _, _, w in ts] for n, ts in toks.items()}, glossary)

    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, "urn:cts:angLit:anon.beowulf", "Beowulf Manuscript", "Beowulf", "verse", "epic",
         "urn:cts:angLit:anon.beowulf.perseus-ang1", "urn:cts:angLit:anon.beowulf.perseus-eng1",
         "James M. Garnett", "complete", "treebank", "ang", CREDIT)).lastrowid
    stats = Counter()
    readings = defaultdict(Counter)     # form key -> Counter((lemma, key, tag)): for the other poems
    seq = 0
    bl = blocks(lines, english)
    for bi, b in enumerate(bl):
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)", (wid, bi, b["cite_start"], b["cite_end"], b["english"], "[]")).lastrowid
        for k, (n, text, heading) in enumerate(b["lines"]):
            sid = db.execute(
                "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (wid, bid, seq, str(n), n, None, heading, None, 1 if heading else 0, text, "[]")).lastrowid
            seq += 1
            for idx, ((s, e, form), r) in enumerate(zip(toks[n], analysis[n])):
                lemma = key = tag = source = None
                if r:
                    i, tag, how = r
                    entry = glossary.entries[i]
                    lemma, key, source = oe.display_headword(entry["headword"]), entry["key"], "treebank"
                    stats[how] += 1
                    readings[oe.form_key(form)][(lemma, key, tag)] += 1
                else:
                    stats["none"] += 1
                db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                           " VALUES (?,?,?,?,?,?,?,?,?)",
                           (sid, idx, u16(text, s), u16(text, e), form, lemma, key, tag, source))
    total = sum(stats.values())
    return readings, dict(lines=len(lines), blocks=len(bl), tokens=total,
                by_line=f"{100 * stats['line'] / total:.1f}%", by_form=f"{100 * stats['form'] / total:.1f}%",
                none=f"{100 * stats['none'] / total:.1f}%",
                english_lines=len(english), english_missing=sum(1 for n, _, _ in lines if n not in english))


def part_blocks(lines, part, heading):
    """Sentence blocks for one poem (or one riddle, psalm, meter); cites 'part.line'."""
    rows = [(n, text, heading if k == 0 else None) for k, (n, text) in enumerate(lines)]
    out = blocks(rows, {})
    part_blocks.last = out[-1] if out else None
    if part:
        for b in out:
            b["cite_start"], b["cite_end"] = f"{part}.{b['cite_start']}", f"{part}.{b['cite_end']}"
    return out


PART_HEADING = {"riddles": "Riddle {}", "psalms": "Psalm {}", "meters": "Meter {}", "charms": "Charm {}"}


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", oe.form_key(title).replace("æ", "ae").replace("þ", "th")).strip("-")


def build_aspr(db, html_dir, sort, beowulf):
    poems = aspr.read_corpus(html_dir)
    analyser = oe_forms.Analyser(beowulf)
    analyser.train([w for p in poems for _, t in p["lines"] for _, _, w in oe.tokenize(t)])
    works = {}
    for p in poems:
        works.setdefault((p["group"], p["work"]), []).append(p)
    report, analysed = {}, set()
    translations = oe_translations.load()
    for k, ((group, title), parts) in enumerate(works.items()):
        form = parts[0]["form"]
        tr = translations.get(title) or {}
        wid = db.execute(
            "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
            "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sort + k, f"urn:cts:angLit:aspr.{slug(title)}", group, title, "verse", form,
             f"urn:cts:angLit:aspr.{slug(title)}.hidley", tr.get("source", ""), tr.get("translator", ""),
             tr.get("scope", "complete"), "oe-forms", "ang",
             ASPR_CREDIT + (f" English: {tr['translator']}, from {tr['source']} (public domain)." if tr else ""))
        ).lastrowid
        english_lines = 0
        stats, seq, bi = Counter(), 0, 0
        for p in parts:
            heading = PART_HEADING[form].format(p["part"]) if p["part"] and p["part"][0].isdigit() else p["part"]
            own = (tr.get("parts") or {}).get(p["part"] or "", {})
            for b in part_blocks(p["lines"], p["part"], heading):
                first, last = b["lines"][0][0], b["lines"][-1][0]
                if b is part_blocks.last:                     # the translation's own extra lines go with the last block
                    last = max([last] + list(own))
                eng = "\n".join(own[n] for n in range(first, last + 1) if n in own)
                english_lines += sum(1 for n in range(first, last + 1) if n in own)
                bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                                 " VALUES (?,?,?,?,?,?)", (wid, bi, b["cite_start"], b["cite_end"], eng, "[]")).lastrowid
                bi += 1
                for n, text, head in b["lines"]:
                    cite = f"{p['part']}.{n}" if p["part"] else str(n)
                    sid = db.execute(
                        "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,"
                        "text,markers) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (wid, bid, seq, cite, n, None, head, None, 1 if head else 0, text, "[]")).lastrowid
                    seq += 1
                    for idx, (s, e, w) in enumerate(oe.tokenize(text)):
                        rs = analyser.readings(w)
                        lemma = key = tag = None
                        if rs:
                            lemma, key, tag = rs[0]
                            stats["analysed"] += 1
                            if w not in analysed:
                                analysed.add(w)
                                for rank, (l, kk, t) in enumerate(rs):
                                    db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)",
                                               (oe.PREFIX + w, rank, l, kk, oe_forms.describe(t)))
                        elif w[:1].isupper():          # a name: look it up as written
                            lemma, key, tag = w, oe.key(w), "n--------"
                            stats["name"] += 1
                        else:
                            stats["none"] += 1
                        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,'
                                   "source) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (sid, idx, u16(text, s), u16(text, e), w, lemma, key, tag,
                                    "oe-forms" if rs else None))
        total = max(1, sum(stats.values()))
        report[title] = dict(group=group, lines=sum(len(p["lines"]) for p in parts), tokens=total,
                             english=f"{tr['translator']}: {english_lines} lines" if tr else None,
                             analysed=f"{100 * stats['analysed'] / total:.1f}%",
                             names=stats["name"], none=f"{100 * stats['none'] / total:.1f}%")
    return report


def main(sources, out, aspr_html=None):
    db = sqlite3.connect(out)
    sort = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    readings, beowulf = build_beowulf(db, sources, sort)
    report = {"Beowulf": beowulf}
    aspr_html = aspr_html or f"{sources}/cltk_oe/html"
    if os.path.isdir(aspr_html):
        report.update(build_aspr(db, aspr_html, sort + 1, readings))
    else:
        print(f"note: {aspr_html} not found; building Beowulf only", file=sys.stderr)
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
