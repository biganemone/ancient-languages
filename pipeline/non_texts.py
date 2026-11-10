"""Builds the Old Norse texts from the scanned editions, once, into
data/non_texts/<work>.json.gz (committed, public domain), so that the normal
build needs neither the scans nor this script.

  python non_texts.py <scratch dir>

The scratch directory gets the archive.org files (hOCR, ~25 MB each) and the
NeuralMIcePaHC corpus. See non_ocr.py (extraction) and non_correct.py
(correction) for the method.

Output, per work: {"title", "edition", "chapters": [{"n": 1, "heading": str|None,
  "items": [{"kind": "prose", "text": str} | {"kind": "verse", "n": int|None, "lines": [str]}]}],
  "report": {...}}
"""
import gzip
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter

import non_correct as nc
import non_ocr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "non_texts")

SCANS = {
    "njala": "brennunjlssaganj00finn",
    "egils": "egilssagaskallag00finnuoft",     # the 1st edition (1894): its scan reads þ and ð; the 1924 one's does not
    "edda": "eddasnorrasturlu00edda",
}
NMI_URL = ("https://repository.clarin.is/repository/xmlui/bitstream/handle/20.500.12537/20/"
           "NeuralMIcePaHC.zip?sequence=1&isAllowed=y")
NMI = {"njala": "1300.njals.nar-sag", "egils": "1250.egils.nar-sag"}

ROMAN = re.compile(r"^(?:[IVXLC]+|[1l]),\s?(?=[1Il]\.\s)")          # "XII, 1. " opens a chapter
SENTENCE_NO = re.compile(r"(?<![\w.])\d{1,2}\s?\.(?=\s)")             # the editor's sentence numbers


def fetch(url, path):
    if not os.path.exists(path):
        subprocess.run(["curl", "-sfL", "-o", path, url], check=True)
    return path


def scan_file(scratch, ident, suffix):
    """The archive.org file of an item whose name ends in suffix."""
    meta = os.path.join(scratch, f"{ident}_files.json")
    fetch(f"https://archive.org/metadata/{ident}/files", meta)
    names = [f["name"] for f in json.load(open(meta))["result"] if f["name"].endswith(suffix)]
    path = os.path.join(scratch, f"{ident}{suffix}")
    return fetch(f"https://archive.org/download/{ident}/{names[0]}", path)


def witness_words(scratch, key):
    """The NeuralMIcePaHC text: [(word, chapter)]."""
    z = fetch(NMI_URL, os.path.join(scratch, "NeuralMIcePaHC.zip"))
    with zipfile.ZipFile(z) as f:
        text = f.read(f"NeuralMIcePaHC/txt/{key}.txt").decode("utf-8")
    out, chapter = [], 0
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\. kafli\s*(.*)", line)
        if m:
            chapter, line = int(m.group(1)), m.group(2)
        out.extend((w, chapter) for _, _, w in nc.tokens(line))
    return out


def saga_items(lines):
    """Paragraphs and stanzas from the edition's lines, with the chapter marks
    the OCR kept: [{"kind", "text"|"lines", "mark": roman chapter or None, "page"}]."""
    items = []
    for l in lines:
        text = nc.presub(l.text)
        mark = None
        m = ROMAN.match(text)
        if m:
            mark, text = m.group().rstrip(", "), text[m.end():]
        if l.verse:
            sm = re.match(r"^\s*(\d{1,2})\s?\.\s+", text)
            if sm or not items or items[-1]["kind"] != "verse":
                items.append({"kind": "verse", "n": int(sm.group(1)) if sm else None, "lines": [],
                              "mark": mark, "page": l.page})
                if sm:
                    text = text[sm.end():]
            items[-1]["lines"].append(text.strip())
            continue
        text = SENTENCE_NO.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if l.para or mark or not items or items[-1]["kind"] != "prose":
            items.append({"kind": "prose", "lines": [text], "mark": mark, "page": l.page})
        else:
            items[-1]["lines"].append(text)
    for it in items:
        if it["kind"] == "prose":
            it["text"] = nc.drop_stray_marks(non_ocr.join_lines(it.pop("lines")))
    return items


EDDA_PARTS = [(13, "Prologus"), (23, "Gylfaginning"), (120, "Skáldskaparmál"), (307, "Háttatal")]
EDDA_END = 365          # then the index of names and the notes on the verses
NUMBERED = re.compile(r"^\s*(\d{1,3})\s?[.,]\s+")


def is_verse(l):
    """In the Edda the verse is indented less than in the sagas (in
    Skáldskaparmál hardly more than a paragraph), but its lines are short."""
    return l.verse or (l.indent > 0.03 and l.width < 0.78)


def edda_items(lines):
    """Paragraphs and stanzas of the 1907 Edda, each with its part and the
    number printed at its head (a chapter's, or a quoted stanza's: a numbered
    line followed by indented verse)."""
    items = []
    for k, l in enumerate(lines):
        text = nc.presub(l.text)
        letters = sum(c.isalpha() for c in text)
        if letters < max(3, len(text) * 0.5):            # ornaments, stray marks
            continue
        if re.fullmatch(r"(HER HEFR )?[A-ZÁÉÍÓÚÞÆÖ ]{6,}", text.strip()):   # part headings
            continue
        part = [n for start, n in EDDA_PARTS if l.page >= start][-1]
        m = NUMBERED.match(text)
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        if l.verse or (m and nxt is not None and is_verse(nxt)) or (is_verse(l) and items and items[-1]["kind"] == "verse"):
            if (m or not items or items[-1]["kind"] != "verse" or items[-1]["part"] != part
                    or (items[-1]["page"] != l.page and False)):
                items.append({"kind": "verse", "n": int(m.group(1)) if m else None, "lines": [],
                              "part": part, "page": l.page, "num": None})
                if m:
                    text = text[m.end():]
            items[-1]["lines"].append(text.strip())
            continue
        num = None
        if m and l.para:
            num, text = int(m.group(1)), text[m.end():]
        text = re.sub(r"\s+", " ", text).strip()
        if l.para or num is not None or not items or items[-1]["kind"] != "prose" or items[-1]["part"] != part:
            items.append({"kind": "prose", "lines": [text], "part": part, "page": l.page, "num": num})
        else:
            items[-1]["lines"].append(text)
    for it in items:
        if it["kind"] == "prose":
            it["text"] = nc.drop_stray_marks(non_ocr.join_lines(it.pop("lines")))
    return items


def edda_chapters(items):
    """Parts and chapters: a chapter starts at a numbered paragraph whose number
    follows the part's last chapter (in Skáldskaparmál the numbers of the quoted
    stanzas run alongside); Háttatal is divided by its stanzas."""
    parts = []
    for it in items:
        if not parts or parts[-1]["title"] != it["part"]:
            parts.append({"title": it["part"], "chapters": []})
        chapters = parts[-1]["chapters"]
        n = None
        if it["part"] == "Háttatal":
            if it["kind"] == "verse" and it["n"] and (not chapters or chapters[-1]["n"] < it["n"] <= chapters[-1]["n"] + 5):
                n = it["n"]
        elif it["kind"] == "prose" and it["num"] and (
                not chapters or chapters[-1]["n"] < it["num"] <= chapters[-1]["n"] + 5):   # (numbers the OCR lost)
            n = it["num"]
        if n is not None or not chapters:
            first = 0 if it["part"] == "Háttatal" else 1      # Háttatal's opening prose comes before stanza 1
            chapters.append({"n": n if n is not None else (chapters[-1]["n"] + 1 if chapters else first),
                             "heading": None, "items": []})
        elif it["kind"] == "prose" and it["num"]:          # a number that is not the next chapter's: keep it
            it["text"] = f"{it['num']}. {it['text']}"
        chapters[-1]["items"].append({"kind": "prose", "text": it["text"]} if it["kind"] == "prose"
                                     else {"kind": "verse", "n": it["n"], "lines": it["lines"]})
    return parts


def google_words(scratch, ident):
    """The words of a plain-text scan (no layout): running heads and page numbers dropped."""
    path = scan_file(scratch, ident, "_djvu.txt")
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or re.fullmatch(r"(\d+\s+)?[A-ZÁÉÍÓÚÞÆÖ. ]{4,}(\s+\d+)?", line):
            continue
        out.extend((w, None) for _, _, w in nc.tokens(nc.presub(line)))
    return out


def build_edda(scratch, vocab):
    pages = non_ocr.read_hocr(scan_file(scratch, SCANS["edda"], "_hocr.html"))
    lines = non_ocr.text_lines(pages, EDDA_PARTS[0][0], EDDA_END)
    items = edda_items(lines)
    witness = google_words(scratch, "eddasnorrasturl00sturgoog")
    sc = SagaCorrection(items, witness, vocab, oldnorse_o="ö", learn=False)
    sc.match()
    stats, *_ = sc.finish()
    parts = edda_chapters(items)
    total = sum(stats.values())
    report = {k: f"{100 * v / total:.1f}%" for k, v in stats.items()}
    report.update(words=total, parts={p["title"]: len(p["chapters"]) for p in parts})
    return {"title": "Edda Snorra Sturlusonar",
            "edition": "Finnur Jónsson, Edda Snorra Sturlusonar (Reykjavík: Sigurður Kristjánsson, 1907)",
            "parts": parts, "report": report}


def item_words(items):
    """All the words of the items in order: [(item index, line index or None, start, end, word)]."""
    out = []
    for k, it in enumerate(items):
        if it["kind"] == "prose":
            out.extend((k, None, s, e, w) for s, e, w in nc.tokens(it["text"]))
        else:
            for li, line in enumerate(it["lines"]):
                out.extend((k, li, s, e, w) for s, e, w in nc.tokens(line))
    return out


class SagaCorrection:
    """Two passes, so that every saga's well-attested words are in the
    vocabulary before any saga's unmatched words are repaired from it:
    match() repairs the words the witness covers and adds the exact matches
    to the vocabulary; finish() repairs the rest and writes the text back."""

    def __init__(self, items, witness, vocab, oldnorse_o="ǫ", learn=True):
        self.items, self.witness, self.vocab, self.o, self.learn = items, witness, vocab, oldnorse_o, learn

    def match(self):
        self.words = item_words(self.items)
        ocr = [w for *_, w in self.words]
        wit = [w for w, _ in self.witness]
        pairs = nc.align(ocr, wit)
        self.exact = dict(pairs)
        self.matched = dict(pairs + nc.fuzzy_pairs(ocr, wit, pairs))
        self.fixed = [nc.repair_best(w, wit[self.matched[i]], self.o) if i in self.matched else None
                      for i, w in enumerate(ocr)]
        if self.learn:
            self.vocab.add(r for i, r in enumerate(self.fixed) if i in self.exact)

    def finish(self):
        return correct_saga(self)


def correct_saga(sc):
    """Repairs the items' words in place; returns (stats, matched words per item,
    words per item, witness chapter per item)."""
    items, words, witness, vocab = sc.items, sc.words, sc.witness, sc.vocab
    match, exact = sc.matched, sc.exact
    fixed = []
    stats = Counter()
    for i, (*_rest, w) in enumerate(words):
        if i in match:
            r = sc.fixed[i]
            stats["exact" if i in exact else "fuzzy"] += 1
            if not sc.learn:
                # both scans can lose the same accent (nu, i): a known word differing only in accents
                known = vocab.by_fold.get(nc.fold(r))
                if known and r not in known and r.lower() not in known:
                    top, n = known.most_common(1)[0]
                    top = top.replace("ǫ", sc.o).replace("Ǫ", sc.o.upper())
                    if n >= 5 and nc.strip_accents(top).lower() == nc.strip_accents(r).lower() and r[0].islower() == top[0].islower():
                        r = top
        else:
            best = vocab.best(w)
            if best and sc.o != "ǫ":                      # the vocabulary is in the sagas' spelling
                best = best.replace("ǫ", sc.o).replace("Ǫ", sc.o.upper())
            r = nc.repair(w, best, sc.o) if best else w
            stats["vocab" if best else "none"] += 1
        if re.match(r"^[60](?=[ðd])", r):                    # 6ðinn, 0ðru: Óðinn, öðru (whichever is known)
            known = vocab.by_fold.get(nc.fold("o" + r[1:]))
            if re.match(r"^.ð(in|n)", r):
                r = "Ó" + r[1:]
            elif known:
                r = known.most_common(1)[0][0].replace("ǫ", sc.o).replace("Ǫ", sc.o.upper())
            else:
                r = sc.o + r[1:]
        if nc.fold(r) in ("odinn", "odins", "odni"):        # the god's name, always capitalized
            r = "Ó" + r[1:]
        fixed.append(r)
    # German from the notes run into a line of the text: runs of unmatched words with German in them
    run = []
    for i in range(len(words) + 1):
        if i < len(words) and i not in match and words[i][:2] == (words[run[0]][:2] if run else words[i][:2]):
            run.append(i)
            continue
        if len(run) >= 3 and sum(non_ocr.german_word(words[j][-1]) for j in run) >= max(1, len(run) // 4):
            for j in run:
                fixed[j] = ""
            stats["german"] += len(run)
        run = [i] if i < len(words) and i not in match else []
    # write the repaired words back (right to left within each piece of text)
    by_piece = {}
    for (k, li, s, e, _), r in zip(words, fixed):
        by_piece.setdefault((k, li), []).append((s, e, r))
    for (k, li), reps in by_piece.items():
        text = items[k]["text"] if li is None else items[k]["lines"][li]
        for s, e, r in sorted(reps, reverse=True):
            text = text[:s] + r + text[e:]
        text = re.sub(r"\s{2,}", " ", re.sub(r"\s+([,.;:])(?=\s*[,.;:]|\s*$)", "", text)).strip()
        if li is None:
            items[k]["text"] = text
        else:
            items[k]["lines"][li] = text
    # each item's share of matched words, and the witness chapter most of its matches are in
    share, votes = Counter(), {}
    for i, (k, *_rest) in enumerate(words):
        if i in match:
            share[k] += 1
            votes.setdefault(k, Counter())[witness[match[i]][1]] += 1
    chap = {k: v.most_common(1)[0][0] for k, v in votes.items()}
    totals = Counter(k for k, *_ in words)
    return stats, share, totals, chap


def roman(s):
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    s = s.replace("l", "I").replace("1", "I")
    if not s or any(c not in vals for c in s):
        return None
    n = 0
    for a, b in zip(s, s[1:] + " "):
        n += -vals[a] if b != " " and vals[a] < vals[b] else vals[a]
    return n


def chapters_of(items, share, totals, chap):
    """Groups the items into the witness's chapters. Items before the first
    and after the last matched one (title pages, index) and items with almost
    nothing matched (notes that slipped through) are dropped; verse is kept
    (it is printed in older spelling and matches less)."""
    keep = [k for k in range(len(items)) if totals[k] and (
        share[k] / totals[k] >= 0.35 or (items[k]["kind"] == "verse" and share[k] / totals[k] >= 0.1))]
    if not keep:
        return []
    first, last = keep[0], keep[-1]
    chapters, current = [], None
    for k in range(first, last + 1):
        if k not in keep:
            continue
        n = chap.get(k)
        mark = roman(items[k]["mark"]) if items[k].get("mark") else None
        if mark and (current is None or mark == current["n"] + 1):      # the edition's own chapter number
            n = mark
        if n is not None and (current is None or n > current["n"]) and (
                n <= (current["n"] if current else 0) + 3):             # (not a stray match far ahead)
            current = {"n": n, "heading": None, "items": []}
            chapters.append(current)
        elif current is None:
            current = {"n": 1, "heading": None, "items": []}
            chapters.append(current)
        it = items[k]
        current["items"].append({"kind": "prose", "text": it["text"]} if it["kind"] == "prose"
                                else {"kind": "verse", "n": it["n"], "lines": it["lines"]})
    return chapters


def split_at_chapters(items, witness):
    """Splits prose items where a new chapter of the witness begins inside them
    (the OCR missed the paragraph break), at a sentence end near that word."""
    words = item_words(items)
    ocr = [w for *_, w in words]
    match = dict(nc.align(ocr, [w for w, _ in witness]))
    cuts = {}
    last = 0
    for i, (k, li, s, e, w) in enumerate(words):
        if i not in match:
            continue
        c = witness[match[i]][1]
        # a new chapter, confirmed by the next few matched words
        if c == last + 1 and li is None:
            ahead = [witness[match[j]][1] for j in range(i, min(i + 8, len(words))) if j in match]
            if ahead.count(c) >= len(ahead) * 0.6:
                text = items[k]["text"]
                cut = max(text.rfind(". ", 0, s + 1), text.rfind(": ", 0, s + 1), text.rfind("; ", 0, s + 1))
                cut = cut + 2 if cut >= 0 and s - cut < 40 else s
                if cut > 0:
                    cuts.setdefault(k, []).append(cut)
        if c > last:
            last = c
    out = []
    for k, it in enumerate(items):
        if k not in cuts or it["kind"] != "prose":
            out.append(it)
            continue
        text, prev = it["text"], 0
        for c in sorted(set(cuts[k])):
            if text[prev:c].strip():
                out.append(dict(it, text=text[prev:c].strip()))
            prev = c
        out.append(dict(it, text=text[prev:].strip(), mark=None))
    return out


def prepare_saga(scratch, key, vocab):
    pages = non_ocr.read_hocr(scan_file(scratch, SCANS[key], "_hocr.html"))
    lines = non_ocr.text_lines(pages)
    witness = witness_words(scratch, NMI[key])
    items = split_at_chapters(saga_items(lines), witness)
    sc = SagaCorrection(items, witness, vocab)
    sc.match()
    return sc


def finish_saga(sc, title, edition):
    items, witness = sc.items, sc.witness
    stats, share, totals, chap = sc.finish()
    chapters = chapters_of(items, share, totals, chap)
    total = sum(stats.values())
    report = {k: f"{100 * v / total:.1f}%" for k, v in stats.items()}
    report.update(chapters=len(chapters), words=total,
                  witness_chapters=max(c for _, c in witness),
                  verses=sum(1 for c in chapters for it in c["items"] if it["kind"] == "verse"))
    return {"title": title, "edition": edition, "chapters": chapters, "report": report}


def save(name, data):
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, f"{name}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


SAGAS = (("njala", "Brennu-Njáls saga",
          "Finnur Jónsson, Brennu-Njálssaga (Njála), Altnordische Saga-Bibliothek 13 (Halle, 1908)"),
         ("egils", "Egils saga Skalla-Grímssonar",
          "Finnur Jónsson, Egils saga Skallagrímssonar, Altnordische Saga-Bibliothek 3 (Halle, 1894)"))


def main(scratch):
    os.makedirs(scratch, exist_ok=True)
    vocab = nc.Vocabulary()
    prepared = [(prepare_saga(scratch, key, vocab), key, title, edition) for key, title, edition in SAGAS]
    for sc, key, title, edition in prepared:
        data = finish_saga(sc, title, edition)
        save(key, data)
        print(key, json.dumps(data["report"], ensure_ascii=False))
    data = build_edda(scratch, vocab)
    save("snorra_edda", data)
    print("snorra_edda", json.dumps(data["report"], ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
