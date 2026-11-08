"""Seven principal Upanishads from the Digital Corpus of Sanskrit (Oliver
Hellwig, CC BY 4.0), divided into numbered sections and verses, with Max
Müller's translations (Sacred Books of the East 1 and 15, 1879–84, public
domain) as English.

  python build_upanishads.py <sources> <texts.db>        (after build_sanskrit.py)

- DCS gives each chapter (khaṇḍa, brāhmaṇa, vallī…) as a file of sentences.
  Section and verse numbers come from aligning with a numbered text
  (upanishad_editions.py), as for the Gītā; DCS's own counters only where
  there is none (Taittirīya 3.3).
- Words DCS lacks entirely (Chāndogya 2.13–14 are not annotated) are added
  from the numbered text, unanalysed.
- One block per section (prose) or verse; verses keep their half-lines.
- Not here: Kauṣītaki (DCS has two of its four chapters); Īśa, Kena, Praśna
  and Māṇḍūkya (not in DCS).
"""
import glob
import gzip
import json
import os
import re
import sqlite3
import sys
from collections import Counter, OrderedDict, defaultdict

import sanskrit as S
import upanishad_editions as U
from build_sanskrit import add_unit, chapter, save_lemma_ids

HERE = os.path.dirname(os.path.abspath(__file__))
CREDIT = ("Sanskrit: the Digital Corpus of Sanskrit (Oliver Hellwig), text and analyses, CC BY 4.0; sections "
          "numbered by alignment with the mūla text of Śaṅkara's commentaries (GRETIL, via the DCS repository) "
          "or Sanskrit Wikisource. English: F. Max Müller, The Upanishads (Sacred Books of the East 1 and 15, "
          "1879–84), public domain.")

# (DCS folder, title, verse?, how chapters are named, English key)
WORKS = [
    ("Kaṭhopaniṣad", "Kaṭha Upaniṣad", True, ("Adhyāya", "Vallī"), "katha"),
    ("Muṇḍakopaniṣad", "Muṇḍaka Upaniṣad", True, ("Muṇḍaka", "Khaṇḍa"), "mundaka"),
    ("Taittirīyopaniṣad", "Taittirīya Upaniṣad", False, ("Vallī", "Anuvāka"), "taittiriya"),
    ("Aitareyopaniṣad", "Aitareya Upaniṣad", False, ("Adhyāya", "Khaṇḍa"), "aitareya"),
    ("Chāndogyopaniṣad", "Chāndogya Upaniṣad", False, ("Prapāṭhaka", "Khaṇḍa"), "chandogya"),
    ("Bṛhadāraṇyakopaniṣad", "Bṛhadāraṇyaka Upaniṣad", False, ("Adhyāya", "Brāhmaṇa"), "brihadaranyaka"),
    ("Śvetāśvataropaniṣad", "Śvetāśvatara Upaniṣad", True, ("Adhyāya",), "svetasvatara"),
]


def chapter_key(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## chapter:"):
                return ".".join(p.strip() for p in line.split(":", 1)[1].split(",")[1:])
    return ""


def kaha_key(key):
    """Kaṭha: DCS numbers the vallīs 1–6; cited as adhyāya.vallī (1.1–1.3, 2.1–2.3)."""
    n = int(key)
    return f"{1 if n <= 3 else 2}.{n if n <= 3 else n - 3}"


def by_counter(sents, key):
    """Sections from DCS's own sentence counters: [(cite, [line: [group]])]."""
    out = OrderedDict()
    last = "1"
    for s in sents:
        c = s.get("counter") or last
        last = c
        out.setdefault(f"{key}.{c}", []).append(s["groups"])
    return list(out.items())


def assign_english(units, eng):
    """English for a chapter's sections. Müller's section numbers mostly match
    the Sanskrit's; where a chapter's counts differ (Müller numbers the
    lineage lists item by item; some editions divide sections differently),
    his paragraphs go to the sections they fall in by position, measured in
    letters through the chapter."""
    if not units:
        return {}
    chap = units[0][0].rsplit(".", 1)[0]
    mine = [(c, t) for c, t in eng.items() if c.rsplit(".", 1)[0] == chap]
    cites = [c for c, _ in units]
    if len(mine) == len(cites) and all(c in eng for c in cites):
        return {c: eng[c] for c in cites}
    if not mine:
        return {}
    size = [max(1, sum(len(g["form"]) for l in lines for g in l)) for _, lines in units]
    total = sum(size)
    bounds, acc = [], 0
    for n in size:
        acc += n
        bounds.append(acc / total)
    etotal = sum(len(t) for _, t in mine) or 1
    out, acc = {}, 0
    for _, t in mine:
        mid = (acc + len(t) / 2) / etotal
        acc += len(t)
        j = next(i for i, b in enumerate(bounds) if mid <= b + 1e-9)
        out[cites[j]] = (out.get(cites[j], "") + " " + t).strip()
    return out


def build(sources, out):
    db = sqlite3.connect(out)
    editions = U.load(sources, os.path.join(HERE, "data"))
    english = {}
    path = os.path.join(HERE, "data", "upanishads_muller.json.gz")
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            english = json.load(f)
    root = os.path.join(sources, "dcs", "dcs", "data", "conllu", "files")
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    lemma_ids = Counter()
    report = {}
    for k, (folder, title, verse, names, ekey) in enumerate(WORKS):
        files = sorted(glob.glob(os.path.join(root, folder, "*.conllu")))
        if not files:
            continue
        slug = re.sub(r"[^a-z]", "", ekey)
        wid = db.execute(
            "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
            "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start + k, f"urn:san:dcs.{slug}", "Upaniṣads", title, "prose", "chapters", f"urn:san:dcs.{slug}.dcs",
             "", "F. Max Müller", "complete", "dcs", "san", CREDIT)).lastrowid
        ed = editions.get(folder)
        cites_in_ed = {c: lines for v in (ed or {}).values() for c, lines in v}
        eng = english.get(ekey, {})
        stats = Counter()
        seq = bseq = 0
        heading_shown = set()
        for path in files:
            key = chapter_key(path)
            sents = S.read_conllu(path, counters=True)
            sections = (ed or {}).get(key) or ([(key, cites_in_ed[key])] if key in cites_in_ed else None)
            if sections:
                units = chapter(sents, sections)
                stats["aligned_chapters"] += 1
            else:
                units = by_counter(sents, key)
                stats["counted_chapters"] += 1
            if folder == "Kaṭhopaniṣad":           # vallī 1–6 -> adhyāya.vallī (1.1–2.3)
                units = [(kaha_key(c.split(".")[0]) + "." + c.split(".", 1)[1], l) for c, l in units]
            kept = []
            for cite, lines in units:
                lines = [l for l in lines if l]
                if not lines:
                    stats["empty_sections"] += 1
                    continue
                kept.append((cite, lines))
            english_for = assign_english(kept, eng)
            for cite, lines in kept:
                if not verse:                       # prose: a section is one paragraph
                    lines = [[g for l in lines for g in l]]
                chap = cite.rsplit(".", 1)[0] if cite.count(".") >= 1 else cite
                hkey = chap if len(names) > 1 and chap.count(".") >= 1 else chap.split(".")[0]
                heading = None
                if hkey not in heading_shown:
                    heading_shown.add(hkey)
                    top = hkey.split(".")[0]
                    heading = f"{names[0]} {top}" if len(names) == 1 or "." not in hkey \
                        else f"{names[0]} {top}, {names[1]} {hkey.split('.')[1]}"
                add_unit(db, wid, bseq, seq, cite, cite.rsplit(".", 1)[-1], lines, english_for.get(cite, ""), heading,
                         stats, lemma_ids)
                bseq += 1
                seq += 1
                stats["sections"] += 1
        report[title] = dict(stats)
    save_lemma_ids(db, lemma_ids)
    db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    build(*sys.argv[1:3])
