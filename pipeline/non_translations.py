"""The English translations of the Old Norse prose texts, by chapter, into
data/non_translations.json.gz (committed; public domain). Run once:

  python non_translations.py <scratch dir>

  - Njáls saga: George Webbe Dasent, The Story of Burnt Njal (1861), Project
    Gutenberg #17919.
  - Egils saga: W. C. Green, The Story of Egil Skallagrimsson (1893),
    archive.org thestoryofegilskallagrigreen (OCR).
  - Snorra Edda: Arthur Gilchrist Brodeur, The Prose Edda (1916), archive.org
    proseedda00snor (OCR): the Prologue, Gylfaginning and Skáldskaparmál
    (Brodeur leaves out Háttatal). Translated from Finnur Jónsson's edition,
    so its chapters are his.

The translators divide the sagas a little differently from the Old Norse
texts here (whose chapters are the modern editions'), so their chapters are
matched to ours by the people and places they name (align()).

Output: {work: {"translator", "source", "chapters": [{"n": the Old Norse chapter,
  "english": [paragraph, …]}]}}; for the Edda, "parts": {part: [{"n", "english"}]}.
"""
import gzip
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "non_translations.json.gz")
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(s):
    s = s.replace("l", "I").replace("1", "I").replace("n", "II")         # (OCR: "XLVn." for XLVII)
    if not s or any(c not in ROMAN for c in s):
        return None
    n = 0
    for a, b in zip(s, s[1:] + " "):
        n += -ROMAN[a] if b != " " and ROMAN[a] < ROMAN[b] else ROMAN[a]
    return n


def fetch(url, path):
    if not os.path.exists(path):
        subprocess.run(["curl", "-sfL", "-A", "Mozilla/5.0", "-o", path, url], check=True)
    return path


def archive_text(scratch, ident):
    meta = fetch(f"https://archive.org/metadata/{ident}/files", os.path.join(scratch, f"{ident}_files.json"))
    name = next(f["name"] for f in json.load(open(meta))["result"] if f["name"].endswith("_djvu.txt"))
    return open(fetch(f"https://archive.org/download/{ident}/{name}", os.path.join(scratch, f"{ident}.txt")),
                encoding="utf-8", errors="replace").read()


def paragraphs(block):
    """Paragraphs from text with blank lines between them; lines joined, words
    broken at a line end rejoined."""
    out = []
    for p in re.split(r"\n\s*\n", block):
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if not lines:
            continue
        text = ""
        for l in lines:
            if text.endswith("-") and not text.endswith("--"):
                text = text[:-1] + l
            else:
                text = f"{text} {l}" if text else l
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def ocr_paragraphs(block):
    """Paragraphs from OCR text that has a blank line after every line: a
    paragraph ends at a short line that ends a sentence."""
    lines = [re.sub(r"^\d{1,2}\s+(?=[a-z])", "", l.strip()) for l in block.splitlines() if l.strip()]
    if not lines:
        return []
    typical = sorted(len(l) for l in lines)[len(lines) // 2]
    out, cur = [], ""
    for l in lines:
        if cur.endswith("-") and not cur.endswith("--"):
            cur = cur[:-1] + l
        else:
            cur = f"{cur} {l}" if cur else l
        if len(l) < typical * 0.75 and re.search(r"[.!?][\"'”’]?$", l):
            out.append(re.sub(r"\s+", " ", cur).strip())
            cur = ""
    if cur.strip():
        out.append(re.sub(r"\s+", " ", cur).strip())
    return out


# ------------------------------------------------------------------ Dasent --
def dasent(scratch):
    t = open(fetch("https://www.gutenberg.org/cache/epub/17919/pg17919.txt",
                   os.path.join(scratch, "dasent.txt")), encoding="utf-8").read()
    t = t.replace("\r\n", "\n")
    t = t[:t.find("*** END OF")] if "*** END OF" in t else t
    t = re.sub(r"\[Footnote[^\]]*\]", "", t, flags=re.S)           # footnotes
    t = re.sub(r"\[\d+\]", "", t)                                    # their markers
    parts = re.split(r"^CHAPTER ([IVXLC]+)\.\s*$", t, flags=re.M)
    chapters = []
    for num, body in zip(parts[1::2], parts[2::2]):
        paras = paragraphs(body)
        title = paras.pop(0).rstrip(".") if paras and paras[0].isupper() else None
        chapters.append({"n": roman(num), "title": title, "english": paras})
    # the last chapter ends the book: drop anything after it that is not the saga
    return chapters


# ------------------------------------------------------------------- Green --
def clean_ocr_lines(text, heads):
    """Drops running heads, page numbers and footnotes from an OCR'd English book."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if re.fullmatch(r"[\divxlc]{1,5}", s.lower()):                      # page numbers
            out.append("")
            continue
        if any(re.match(h, s) for h in heads) and not s.startswith("CHAPTER"):
            out.append("")
            continue
        if re.match(r"^(\^|\*|†|\d{1,2}\s+(?=[A-Z])|[¹²³])", s) and len(s) < 300:   # footnotes ("1 Lit. …")
            out.append("")
            continue
        s = re.sub(r"^\d{1,2}\s+(?=[a-z])", "", s)                               # a stray number before the text
        out.append(s)
    return "\n".join(out)


DROP_CAP = {"HERE": "THERE", "HEN": "THEN", "RIM": "GRIM", "ING": "KING", "HORSTEIN": "THORSTEIN",
            "HOROLF": "THOROLF", "HORIR": "THORIR", "OW": "NOW", "FTER": "AFTER", "HAT": "THAT"}


def drop_cap(p):
    """The OCR loses a chapter's large initial and puts it a few words on as a
    stray capital ("UDBJORN was … there was A an earl", "Firths, kK whence"):
    restore it, and set the opening words in capitals as ordinary words.
    Returns (title or None, paragraph): a short title the OCR ran into the
    paragraph ("The beginning of the rule of Harold Fairhair. AROLD, son …")."""
    m = re.search(r"\b([A-Z]{2,})\b", p[:90])
    if not m:
        return None, p
    before, title = p[:m.start()], None
    if re.search(r"[a-z]{3}.*[.!?]\s*$", before):          # a title sentence
        title, p = before.strip(), p[m.start():]
    else:                                                  # junk before the word: ". d ING"
        p = p[m.start():]
    caps = re.match(r"^((?:[A-Z][A-Z'’]+\s*)+)", p)
    opening, rest = caps.group(1).strip(), p[caps.end():]
    first = opening.split()[0]
    stray = re.search(r"(?<=\s)[a-z]?([A-Z])(?=[\s,;])", rest[:140])
    if first in DROP_CAP:
        opening = DROP_CAP[first] + opening[len(first):]
    elif stray and stray.group(1) != "I":
        opening = stray.group(1) + opening
        rest = rest[:stray.start()] + rest[stray.end():]
    opening = " ".join(w.capitalize() if w.isupper() else w for w in opening.split())
    return title, re.sub(r"\s+", " ", f"{opening} {rest.lstrip()}").replace(" ,", ",").replace(" ;", ";")


def green(scratch):
    t = archive_text(scratch, "thestoryofegilskallagrigreen")
    start = t.find("CHAPTER I.")
    t = t[start:]
    end = re.search(r"\n\s*(INDEX|APPENDIX|NOTES)\b", t)
    if end:
        t = t[:end.start()]
    t = clean_ocr_lines(t, [r"^(\d+\s+)?(EGIL'?S SAGA|THE STORY OF EGIL|CHAP\.\s*[IVXLC]+)\.?(\s+\d+)?$",
                            r"^[A-Z][A-Z' .,;-]{8,}(\s+\d+)?$"])
    parts = re.split(r"^\s*CHAPTER\s+([IVXLC1l]+)\s*\.?.*$", t, flags=re.M)
    chapters = []
    for k, (num, body) in enumerate(zip(parts[1::2], parts[2::2])):
        paras = ocr_paragraphs(body)
        title = paras.pop(0) if paras and len(paras[0]) < 80 else None      # "Of Kveldulf and his sons."
        if paras:
            t2, paras[0] = drop_cap(paras[0])
            title = title or t2
        chapters.append({"n": k + 1, "printed": num, "title": title, "english": paras})
    return chapters


# ----------------------------------------------------------------- Brodeur --
def brodeur(scratch):
    t = archive_text(scratch, "proseedda00snor")
    heads = [r"^(\d+\s+)?(THE PROSE EDDA|PROLOGUE|GYLFAGINNING|THE BEGUILING OF GYLFI|SKALDSKAPARMAL|"
             r"THE POESY OF SKALDS)\.?(\s+\d+)?$"]
    # the translation: from the Prologue's first line to the index
    begin = t.find("PROLOGUE", t.find("PROLOGUE", t.find("PROLOGUE") + 1) + 1)
    end = t.find("\nINDEX", begin)
    body = clean_ocr_lines(t[begin:end], heads)
    out = {"Prologus": [], "Gylfaginning": [], "Skáldskaparmál": []}
    # chapters: a Roman numeral and a full stop at the head of a paragraph;
    # Gylfaginning's run from I, then Skáldskaparmál's start again from I
    pieces = re.split(r"(?:^|\n)([IVXLC]{1,6}n?)\.\s+(?=\S)", body)
    out["Prologus"].append({"n": 1, "english": paragraphs(pieces[0])})
    part, last = "Gylfaginning", 0
    for num, text in zip(pieces[1::2], pieces[2::2]):
        n = roman(num)
        if n is None:
            continue
        if part == "Gylfaginning" and n == 1 and last > 40:
            part, last = "Skáldskaparmál", 0
        if n <= last or n > last + 4:          # a numeral that is not a chapter's (in a list, a citation)
            if out[part]:
                out[part][-1]["english"].extend(paragraphs(f"{num}. {text}"))
            continue
        out[part].append({"n": n, "english": paragraphs(text)})
        last = n
    return out


# --------------------------------------------------------------- alignment --
def name_key(w):
    """A name reduced so that the Old Norse and the translators' spellings meet:
    Þórólfr, Thorolf -> thorol; Hǫskuldr, Hauskuld -> hosku."""
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    w = (w.replace("þ", "th").replace("ð", "d").replace("ǫ", "o").replace("ø", "o").replace("æ", "ae")
         .replace("œ", "oe").replace("au", "o").replace("ey", "e").replace("j", "i"))
    return w[:5]


def names(text, stop):
    ws = re.findall(r"(?<![.!?„\"]\s)(?<!^)\b[A-ZÁÉÍÓÚÝÞÆÖǪØ][a-záéíóúýþðæöǫøœ]{2,}", text)
    return Counter(name_key(w) for w in ws if name_key(w) not in stop)


def align(norse, english):
    """{english chapter index: Old Norse chapter number}: a monotone alignment
    maximizing the names the two share (weighted by how rare they are)."""
    stop = {"there", "then", "this", "that", "when", "they", "their", "after", "now", "but", "and", "the"}
    nn = [names(t, stop) for _, t in norse]
    en = [names(t, stop) for t in english]
    df = Counter(k for c in nn for k in c)
    idf = {k: math.log(len(nn) / v) for k, v in df.items()}

    def sim(i, j):
        return sum(min(nn[i][k], en[j][k]) * idf.get(k, 0) for k in nn[i] if k in en[j])

    # one-to-one, best matches first (the translators sometimes order chapters
    # differently: Dasent puts the conversion before Lýtingr's attack), with a
    # mild preference for chapters at about the same place in the book
    I, J = len(nn), len(en)
    scored = []
    for i in range(I):
        for j in range(J):
            s = sim(i, j)
            if s > 0:
                scored.append((s * math.exp(-4 * abs(i / I - j / J)), i, j))
    pairs, used = {}, set()
    for s, i, j in sorted(scored, reverse=True):
        if j not in pairs and i not in used:
            pairs[j] = i
            used.add(i)
    # english chapters left unmatched go with the Old Norse chapter of the one before
    out, cur = {}, 0
    for j in range(J):
        cur = pairs.get(j, cur)
        out[j] = norse[cur][0]
    return out


def norse_chapters(name):
    d = json.load(gzip.open(os.path.join(HERE, "data", "non_texts", f"{name}.json.gz"), "rt"))
    return [(c["n"], " ".join(it.get("text") or " ".join(it["lines"]) for it in c["items"])) for c in d["chapters"]]


def by_norse(english, mapping):
    """English chapters regrouped under the Old Norse chapters they translate."""
    out = {}
    for j, ch in enumerate(english):
        out.setdefault(mapping[j], []).extend(ch["english"])
    return [{"n": n, "english": paras} for n, paras in sorted(out.items())]


def main(scratch):
    os.makedirs(scratch, exist_ok=True)
    data = {}
    for key, fn, translator, source in (
            ("njala", dasent, "George Webbe Dasent", "The Story of Burnt Njal (1861), Project Gutenberg #17919"),
            ("egils", green, "W. C. Green", "The Story of Egil Skallagrimsson (1893), archive.org"
                                              " thestoryofegilskallagrigreen")):
        english = fn(scratch)
        norse = norse_chapters(key)
        mapping = align(norse, [" ".join(c["english"]) for c in english])
        chapters = by_norse(english, mapping)
        moved = sum(1 for j, c in enumerate(english) if mapping[j] != c["n"])
        data[key] = {"translator": translator, "source": source, "chapters": chapters}
        print(key, f"{len(english)} English chapters -> {len(chapters)} of {len(norse)} Old Norse;"
                   f" {moved} renumbered; empty {[n for n, _ in norse if n not in {c['n'] for c in chapters}][:20]}")
    edda = brodeur(scratch)
    data["snorra_edda"] = {"translator": "Arthur Gilchrist Brodeur",
                           "source": "The Prose Edda (1916), archive.org proseedda00snor", "parts": edda}
    print("snorra_edda", {p: len(c) for p, c in edda.items()},
          {p: sorted(set(range(1, max([x["n"] for x in c] or [0]) + 1)) - {x["n"] for x in c})[:10]
           for p, c in edda.items()})
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main(sys.argv[1])
