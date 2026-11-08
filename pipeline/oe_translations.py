"""Public-domain English translations of Old English poems, from Project
Gutenberg, cut into numbered lines so they can sit beside the ASPR text.

  python oe_translations.py <dir with pg31172.txt, pg15879.txt, pg15225.txt, pg14529.txt>
      writes data/oe_translations.json.gz: {work title: {"translator", "source",
      "scope", "parts": {part or "": {line number: text}}}}

The books (Gutenberg's servers refuse our build machines, so they were saved
through a browser; the extracted lines are kept in data/):
  31172  Faust & Thompson, Old English Poems (1918): alliterative, line for line;
         numbers every fifth line, at the left.
  15879  Garnett, Elene; Judith; Brunanburh; Maldon; The Dream of the Rood
         (1889, 3rd ed. 1911): line for line, numbers at the right.
  15225  Root, Andreas (1899): blank verse, line for line, numbers every tenth.
  14529  Cook & Pitman, The Old English Physiologus (1921): Pitman's verse
         translation, in chunks following chunks of the Old English.

Line numbers are those of each translator's edition; unnumbered lines count
on from the last number, and every printed number resets the count. Editorial
notes ([…] blocks), footnotes and section headings are left out.
"""
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "oe_translations.json.gz")

FT = "Cosette Faust and Stith Thompson (1918)"
GARNETT = "James M. Garnett (1889)"
ROOT = "Robert Kilburn Root (1899)"
PITMAN = "James Hall Pitman (1921)"

# Faust & Thompson: section title in the book -> (our work, part, scope)
FT_POEMS = {
    "WIDSITH": ("Widsith", None, "complete"),
    "DEOR'S LAMENT": ("Deor", None, "complete"),
    "WALDHERE": ("Waldere", None, "complete"),
    "THE FIGHT AT FINNSBURG": ("The Battle of Finnsburh", None, "complete"),
    "CHARMS": ("Metrical Charms", None, "Charms 1 and 4"),
    "RIDDLES": ("Riddles", None, "Selections"),
    "EXETER GNOMES": ("Maxims I", None, "Selections"),
    "THE FATES OF MEN": ("The Fortunes of Men", None, "complete"),
    "THE WANDERER": ("The Wanderer", None, "complete"),
    "THE SEAFARER": ("The Seafarer", None, "Lines 1–64"),
    "THE WIFE'S LAMENT": ("The Wife's Lament", None, "complete"),
    "THE HUSBAND'S MESSAGE": ("The Husband's Message", None, "complete"),
    "THE RUIN": ("The Ruin", None, "complete"),
    "CÆDMON'S HYMN": ("Caedmon's Hymn: West Saxon Version", None, "complete"),
    "BEDE'S DEATH SONG": ("Bede's Death Song: West Saxon Version", None, "complete"),
    "GENESIS A": ("Genesis", None, "Selections"),
    "SELECTIONS FROM EXODUS": ("Exodus", None, "Selections"),
    "SELECTIONS FROM THE CHRIST": ("Christ", None, "Selections"),
    "THE PHOENIX": ("The Phoenix", None, "complete"),
}
# also given to the other versions of the same short poems
ALSO = {"Caedmon's Hymn: West Saxon Version": ["Caedmon's Hymn: Northumbrian Version"],
        "Bede's Death Song: West Saxon Version": ["Bede's Death Song: Northumbrian Version",
                                                  "Bede's Death Song: The Hague Version"]}
FT_CHARMS = {"I": "1", "II": "4"}       # For Bewitched Land, For a Sudden Stitch (ASPR numbers)
GARNETT_POEMS = {"CYNEWULF'S ELENE.": "Elene", "JUDITH.": "Judith", "THE FIGHT AT BRUNANBURH.": "The Battle of Brunanburh",
                 "THE FIGHT AT MALDON.": "The Battle of Maldon", "THE DREAM OF THE ROOD.": "The Dream of the Rood"}
ROMAN = re.compile(r"^(?=[IVXLC]+\b)(M{0,3})(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\.?$")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        t = f.read().replace("\r", "")
    start = t.find("*** START OF")
    end = t.find("*** END OF")
    return t[t.find("\n", start) + 1 if start >= 0 else 0:end if end >= 0 else None]


def clean(text):
    text = re.sub(r"\[\d+\]", "", text)                       # footnote marks
    text = re.sub(r"\[[^\]]*,\s*(Gn|Gm|Z|W|Kl|Gr)\.?\]", "", text)    # Garnett's alternative readings
    text = re.sub(r"_([^_]*)_", r"\1", text)
    text = re.sub(r"\s{3,}", "  ", text.strip())              # half-line gap -> two spaces
    return re.sub(r"[ \t]+([,.;:!?])", r"\1", text).strip()


def number_lines(lines, number_side="left", indented_only=False, start=0):
    """[(n, text)] from raw lines: numbers printed at the left ('5     Travel…')
    or the right ('…by number,     5')."""
    out, n, note, foot = [], start, 0, False
    for raw in lines:
        s = raw.rstrip()
        st = s.strip()
        if not st:
            foot = False
            continue
        if foot:
            continue
        if re.match(r"^\s{2,}\[\d+\]", s) or st.lower().startswith("footnote"):
            foot = True                              # a footnote paragraph
            continue
        if note or (st.startswith("[") and not re.match(r"^\[[^\]]*\]\s*\S", st)):
            note += st.count("[") - st.count("]")    # an editorial note block […]
            if note < 0:
                note = 0
            continue
        if re.match(r"^\*(\s+\*)+$", st) or re.match(r"^(\.\s*){3,}$", st):
            continue
        indent = len(s) - len(s.lstrip())
        if indented_only and indent < 4 and not re.match(r"^\d+\s{2,}\S", s):
            continue                                  # the notes after a poem (at the margin)
        if ROMAN.match(st) or (indent >= 12 and not re.match(r"^\d", st) and len(st) < 60
                               and not re.search(r"\s{3,}", st)):
            continue                                  # a section heading
        num = None
        if number_side == "left":
            m = re.match(r"^\s*(\d+)\s{2,}(.*)$", s)
            if m:
                num, st = int(m.group(1)), m.group(2)
        else:
            m = re.match(r"^(.*?\S)\s{3,}(\d+)$", s)
            if m:
                st, num = m.group(1), int(m.group(2))
        n = num if num is not None else n + 1
        t = clean(st)
        if t:
            out.append((n, t))
    return out


def sections(text, titles):
    """Split the book at the given title lines -> {title: [raw lines]}."""
    lines = text.split("\n")
    marks = [(i, l.strip()) for i, l in enumerate(lines) if l.strip() in titles]
    out = {}
    for k, (i, title) in enumerate(marks):
        j = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        out.setdefault(title, lines[i + 1:j])
    return out


def faust_thompson(path):
    text = read(path)
    text = text[text.find("I. PAGAN POETRY", text.find("PREFACE")):]
    stops = list(FT_POEMS) + ["SELECTIONS FROM GENESIS", "SELECTIONS FROM THE ELENE", "THE DREAM OF THE ROOD",
                              "JUDITH", "THE GRAVE", "III. POEMS FROM THE CHRONICLE", "2. GNOMIC GROUP",
                              "3. ELEGIAC GROUP", "II. CHRISTIAN POETRY", "2. CYNEWULF AND HIS SCHOOL",
                              "APPENDIX--SELECTIONS FROM OLD ENGLISH PROSE"]
    out = {}
    for title, raw in sections(text, set(stops)).items():
        if title not in FT_POEMS:
            continue
        work, _, scope = FT_POEMS[title]
        if title in ("RIDDLES", "CHARMS"):
            # one numbered sub-poem each: "I. A Storm", "14. A Horn", "I. For Bewitched Land"
            parts, cur, key = {}, [], None
            for l in raw:
                m = re.match(r"^\s{10,}([IVXLC]+|\d+)\.\s+\S", l)
                if m:
                    if key:
                        parts[key] = number_lines(cur, indented_only=True)
                    k = m.group(1)
                    key = FT_CHARMS.get(k) if title == "CHARMS" else (str(roman(k)) if ROMAN.match(k) else k)
                    cur = []
                elif key:
                    cur.append(l)
            if key:
                parts[key] = number_lines(cur, indented_only=True)
            parts = {k: v for k, v in parts.items() if k and v}
        elif title == "WALDHERE":
            # two fragments, "I" and "II", each numbered from 1
            chunks, cur = [], []
            for l in raw:
                if re.match(r"^\s{10,}(A|B)\s*$", l):
                    chunks.append(cur)
                    cur = []
                else:
                    cur.append(l)
            chunks.append(cur)
            frags = [number_lines(c, indented_only=True) for c in chunks]
            frags = [f for f in frags if f]
            for name, lines in zip(("Waldere A", "Waldere B"), frags[-2:]):
                out[name] = dict(translator=FT, source="Project Gutenberg #31172", scope="complete",
                                 parts={"": dict(lines)})
            continue
        else:
            parts = {"": number_lines(raw, indented_only=True)}
        out[work] = dict(translator=FT, source="Project Gutenberg #31172", scope=scope,
                         parts={k: dict(v) for k, v in parts.items()})
        for other in ALSO.get(work, []):
            out[other] = out[work]
    return out


def roman(s):
    vals = dict(I=1, V=5, X=10, L=50, C=100)
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


def garnett(path):
    text = read(path)
    text = text[text.find("CYNEWULF'S ELENE."):]
    secs = sections(text, set(GARNETT_POEMS) | {"ATHELSTAN,", "BYRHTNOTH,", "NOTES.", "INDEX."})
    out = {}
    for title, work in GARNETT_POEMS.items():
        if title in secs:
            out[work] = dict(translator=GARNETT, source="Project Gutenberg #15879", scope="complete",
                             parts={"": dict(number_lines(secs[title], "right"))})
    return out


def root_andreas(path):
    text = read(path)
    text = text[text.find("THE LEGEND OF ST. ANDREW", text.find("INTRODUCTION")):]
    text = text[:text.find("\nNOTES")]
    lines = text.split("\n")[1:]
    return {"Andreas": dict(translator=ROOT, source="Project Gutenberg #15225", scope="complete",
                            parts={"": dict(number_lines(lines, "right"))})}


def pitman(path):
    """Old English chunk (numbered), then its verse translation, then Cook's
    prose; the verse chunk takes the line numbers of the Old English before it."""
    text = read(path)
    out = {}
    for title, work in (("THE PANTHER", "The Panther"), ("THE WHALE (ASP-TURTLE)", "The Whale"),
                        ("THE PARTRIDGE[1]", "The Partridge")):
        i = text.find("\n" + title)
        j = min([k for k in (text.find("\nTHE WHALE", i + 10), text.find("\nTHE PARTRIDGE", i + 10),
                             text.find("\nFOOTNOTES", i + 10), len(text)) if k > 0])
        chunks = [c for c in re.split(r"\n\s*\*\s+\*\s+\*\s+\*\s+\*\s*\n", text[i + len(title) + 1:j])]
        lines, last_oe, upto = {}, None, 0
        for k, c in enumerate(chunks):
            oe = number_lines(c.split("\n"), start=upto)
            looks_oe = bool(re.search(r"[þðæāēīōūȳ]", c))
            if looks_oe:
                last_oe = (oe[0][0], oe[-1][0]) if oe else None
                upto = oe[-1][0] if oe else upto
                kind = 0
                continue
            kind = locals().get("kind", 0) + 1
            if kind != 1 or not last_oe:
                continue                                    # Cook's prose: skip
            verse = [clean(l) for l in c.split("\n") if l.strip()]
            a, b = last_oe
            span = b - a + 1
            for m, v in enumerate(verse):                   # spread over the Old English lines
                n = a + min(span - 1, m * span // max(1, len(verse)))
                lines[n] = (lines[n] + " " + v) if n in lines else v
        out[work] = dict(translator=PITMAN, source="Project Gutenberg #14529", scope="complete",
                         parts={"": lines})
    return out


def main(src):
    out = {}
    out.update(faust_thompson(os.path.join(src, "pg31172.txt")))
    out.update(root_andreas(os.path.join(src, "pg15225.txt")))
    out.update(pitman(os.path.join(src, "pg14529.txt")))
    out.update(garnett(os.path.join(src, "pg15879.txt")))      # (preferred where both translate a poem)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    for w, d in out.items():
        n = sum(len(p) for p in d["parts"].values())
        rng = [(k, min(p), max(p)) for k, p in d["parts"].items() if p][:3]
        print(f"{w}: {n} lines {rng} ({d['translator']})", file=sys.stderr)


def load():
    if not os.path.exists(OUT):
        return {}
    with gzip.open(OUT, "rt", encoding="utf-8") as f:
        d = json.load(f)
    for w in d.values():
        w["parts"] = {k: {int(n): t for n, t in p.items()} for k, p in w["parts"].items()}
    return d


if __name__ == "__main__":
    main(sys.argv[1])
