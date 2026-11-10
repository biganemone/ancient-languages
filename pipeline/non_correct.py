"""Correcting the OCR of the Old Norse editions (see non_ocr.py).

The OCR's mistakes are mostly of a few kinds, and systematic: letters it
does not know (ǫ read as o or g, þ as p, J) or |>, ð as d, 3, 5 or Ö),
accents lost or misread (á as å or a, é and ó as 6), and the odd misread
word. So each OCR word is compared with a second witness:

  - for the sagas, the same saga in NeuralMIcePaHC (CC BY 4.0), a different
    edition in modern Icelandic spelling, aligned word by word;
  - for the Prose Edda, a second scan of the same 1907 edition (Google
    Books, archive.org eddasnorrasturl00sturgoog), whose OCR reads þ, ð and
    ö better but loses the ends of lines.

Two words match when they are equal after folding the OCR's confusions and
the differences between modern and normalized Old Norse spelling (fold()).
Then the OCR word is repaired letter by letter from the witness, only where
the two differ by a known confusion (repair()): the edition's own spelling
and readings are kept, and only its letters restored. Words with no match
are repaired from the vocabulary of words already seen (most frequent first),
or left with the character fixes alone.
"""
import difflib
import re
import unicodedata
from collections import Counter, defaultdict

# multi-character OCR renderings of þ/Þ (the Ottawa scans)
THORN_SEQ = [("J)", "þ"), ("|)", "þ"), ("]>", "þ"), ("|>", "þ"), ("f>", "þ"), ("£>", "þ"), ("J>", "þ"),
             ("]3", "þ"), ("J3", "þ"), ("I^", "Þ"), ("t*", "Þ"), ("P*", "Þ"), ("E*", "Þ"), ("}>", "þ"),
             ("}}", "þ"), ("|", "þ")]
WORDCHARS = r"A-Za-zÁÉÍÓÚÝÞÐÆÖØǪŒáéíóúýþðæöøǫœäåàâèêëìîïòôõùûüçñ0-9"
TOKEN = re.compile(rf"[{WORDCHARS}][{WORDCHARS}'’\-]*[{WORDCHARS}]|[{WORDCHARS}]")

# modern Icelandic words and their normalized Old Norse forms (only for matching)
MODERN = {"og": "ok", "að": "at", "það": "þat", "hvað": "hvat", "mig": "mik", "þig": "þik", "sig": "sik",
          "ég": "ek", "hún": "hon", "svo": "svá", "hinn": "inn", "hin": "in", "hið": "it", "hins": "ins",
          "hinum": "inum", "hinnar": "innar", "hina": "ina", "hinir": "inir", "hinna": "inna", "eftir": "eptir",
          "ekki": "eigi", "nokkur": "nǫkkurr", "vera": "vera", "þér": "þér", "er": "er", "mér": "mér",
          "við": "við", "yfir": "yfir", "upp": "upp", "eða": "eða", "þá": "þá", "frá": "frá"}


def strip_accents(s):
    d = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(c for c in d if not unicodedata.combining(c)))


FOLD_MAP = str.maketrans({"ð": "d", "3": "d", "5": "d", "9": "d", "þ": "þ", "p": "þ", "6": "o", "0": "o",
                          "ǫ": "o", "ø": "o", "œ": "æ", "1": "l", "í": "i", "ì": "i", "f": "f", "y": "y",
                          "å": "a", "ä": "a", "à": "a", "â": "a", "ü": "u", "q": "d"})


def fold(word):
    """The word with the OCR's confusions and the modern/Old Norse spelling
    differences folded away, for matching."""
    w = word.lower().replace("’", "").replace("'", "").replace("-", "")
    w = MODERN.get(w, w)
    for a, b in THORN_SEQ:
        w = w.replace(a.lower(), b)
    w = w.replace("oe", "æ").replace("ce", "æ").replace("ae", "æ")
    w = w.translate(FOLD_MAP)
    w = strip_accents(w)
    w = w.replace("ð", "d").replace("ö", "o")
    # Old Norse -r against modern -ur; -ligr against -legur; -sk/-zk against modern -st
    w = re.sub(r"([^aeiouyæ])ur$", r"\1r", w)
    w = re.sub(r"leg", "lig", w)
    w = re.sub(r"(z|s)(t|k)$", "sk", w)
    w = w.replace("ei", "ei").replace("j", "j")
    return w


# letters the OCR confuses with each other: (ocr, true) pairs; a repair from
# the witness is made only across one of these
CONFUSIONS = {
    ("o", "ǫ"), ("o", "ö"), ("o", "ó"), ("g", "ǫ"), ("ç", "ǫ"), ("q", "ǫ"), ("ö", "ǫ"), ("ö", "ó"), ("ö", "ð"),
    ("Ö", "ð"), ("Ö", "Ð"), ("d", "ð"), ("3", "ð"), ("5", "ð"), ("9", "ð"), ("Q", "ð"), ("S", "ð"),
    ("p", "þ"), ("P", "Þ"), ("D", "Þ"), ("b", "þ"), ("a", "á"), ("å", "á"), ("ä", "á"), ("à", "á"),
    ("e", "é"), ("6", "é"), ("6", "ó"), ("i", "í"), ("f", "í"), ("ì", "í"), ("u", "ú"), ("ü", "ú"),
    ("y", "ý"), ("o", "ø"), ("ö", "ø"), ("0", "ø"), ("ce", "œ"), ("oe", "œ"), ("A", "Á"), ("E", "É"),
    ("I", "Í"), ("O", "Ó"), ("U", "Ú"), ("Ü", "Ú"), ("O", "Ǫ"), ("Ö", "Ǫ"), ("Ö", "Ó"),
    ("ó", "é"), ("é", "ó"), ("i", "j"), ("j", "i"), ("í", "j"), ("n", "u"), ("u", "n"), ("b", "h"), ("h", "b"),
    ("c", "e"), ("e", "c"), ("l", "i"), ("t", "f"), ("f", "t"), ("í", "f"), ("f", "í"), ("o", "ð"), ("ö", "ð"),
}


# þ as the OCR renders it: J) |) ]> J? )? }? |? \> p> f> £> J^ … (a stroke or bracket,
# then something like the bow); Þ as I^ t* P* E*
THORN_RE = re.compile(r"(?:(?<=[\s„\"(])|^)[J\]\)\}\|\\£fp][\)\>\?\^3]|[J\]\)\}\|\\][\)\>\?\^]")
CAP_THORN_RE = re.compile(r"(?:(?<=\s)|^)(?:I\^|t\*|P\*|E\*|í>|Í>|D(?=[a-záéíóúýæœǫø]{1,}\b)(?=ei|at|á|ar|ess|ó|ann|eir|enn|vi|er|it|in|a\b))")


# misreadings of more than one letter: (as read, as printed)
MULTI = [("ru", "m"), ("rn", "m"), ("in", "m"), ("ni", "m"), ("iu", "m"), ("cl", "d"), ("li", "h"), ("b", "h"),
         ("n", "u"), ("u", "n"), ("o", "ð"), ("ö", "ð"), ("Ö", "ð"), ("6", "ó"), ("6", "é"), ("<5", "ó"), ("<5", "é"),
         ("í", "f"), ("f", "í"), ("U", "ll"), ("ii", "ü"), ("e", "c"), ("c", "e"), ("i", "l"), ("l", "i"), ("t", "f"),
         ("^", "ǫ"), ("g", "ǫ"), ("q", "ǫ"), ("ç", "ǫ"), ("S", "ð"), ("5", "ð"), ("3", "ð"), ("9", "ð"), ("Q", "ð"),
         ("fi", "ð"), ("b", "ð"), ("d", "ð"), ("oe", "œ"), ("ce", "œ"), ("se", "æ"), ("ae", "æ"), ("ó", "ǫ"),
         ("DD", "nn"), ("D", "n"), ("pY", "þv"), ("Y", "v"), ("K", "l")]
MULTI_SET = set(MULTI)


def presub(text):
    """Fixes that need no witness: the multi-character þ renderings, and
    letters Old Norse does not have (ä, ü) for the ones the OCR meant."""
    text = CAP_THORN_RE.sub("Þ", text)
    text = THORN_RE.sub("þ", text)
    for a, b in THORN_SEQ[:-1]:
        text = text.replace(a, b)
    text = (text.replace("ä", "á").replace("å", "á").replace("Å", "Á").replace("ü", "ú").replace("Ü", "Ú")
            .replace("£", "é"))
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫø])'?Ö", "ð", text)          # Ö inside a word is ð
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫø])t?5(?=[a-záéíóúýþðæœǫø]|\b)", "ð", text)   # and so is (t)5: vit5, met5
    text = re.sub(r"(?<![\w])0(?=[a-záéíóúýæœǫ])", "Ø", text)        # 0xará
    text = re.sub(r"(?<![\w])6(?=[a-záéíóúýþðæœǫö]{2})", "Ó", text)  # 6ðins
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫö])8(?=[a-záéíóúýþðæœǫö]|\b)", "ð", text)   # g68ir
    text = re.sub(r"(?<![\w])\(j(?=[a-z]{2})", "G", text)            # (jylfi
    text = re.sub(r"(?<=[a-zþð])\^(?=[a-zþð])", "ǫ", text)           # and ^ is ǫ
    text = re.sub(r"(?<!\S)\d{3,4}(?:\s?[—–-]\s?\d{1,4})?(?!\S)", "", text)   # the editor's dates (830—40)
    # references to the standard chapters in the margin, run into a word: "varNj. I."
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫ])(?:Nj|Eg|xj|Ej)[.,](?:\s?[IVXLCl]+[.,])?", "", text)
    text = re.sub(r"\s+([;:!?])", r"\1", text)                       # "Berðlu ;" (the period's spacing)
    return text


def drop_stray_marks(text):
    """Sentence numbers the OCR misread as letters ("B." for 3., "Í." for 4.)
    between sentences, and line numbers left inside the text (the prose
    writes its numbers in words or Roman numerals)."""
    text = re.sub(r"(^|(?<=[.;:!?\"“”»] ))[IÍBlSZ1-9]{1,2}[.,] (?=[A-ZÁÉÍÓÚÝÞÆÖǪ„»])", "", text)
    text = re.sub(r"(?<![\w„»\"])\d{1,3}(?![\w])[,.]? ?", "", text)
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫ])DD(?=[a-záéíóúýþðæœǫ]|\b)", "nn", text)       # haDD, manDa
    text = re.sub(r"(?<=[a-záéíóúýþðæœǫ])D(?=[a-záéíóúýþðæœǫ]|\b)", "n", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def repair_best(ocr, witness, oldnorse_o="ǫ"):
    """repair(), first undoing a misreading of more than one letter if that
    makes the OCR word match the witness ("oUu" against öllu: ǫllu)."""
    fw = fold(witness)
    if fold(ocr) != fw:
        for v in Vocabulary.variants(None, ocr):
            if fold(v) == fw:
                return repair(v, witness, oldnorse_o)
    return repair(ocr, witness, oldnorse_o)


def repair(ocr, witness, oldnorse_o="ǫ"):
    """The OCR word with its letters restored from the witness, where the two
    differ by a known confusion. witness is in the target spelling except for
    ö (modern ö is Old Norse ǫ or ø), which becomes oldnorse_o."""
    w = witness.replace("ö", oldnorse_o).replace("Ö", oldnorse_o.upper())
    out = []
    sm = difflib.SequenceMatcher(None, ocr, w, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        a, b = ocr[i1:i2], w[j1:j2]
        if op == "equal":
            out.append(a)
        elif op == "replace" and len(a) == len(b):
            # letter by letter: restore the confusions, keep real differences (mjok/mjög: mjǫk)
            out.append("".join(y if (x, y) in CONFUSIONS else x for x, y in zip(a, b)))
        elif op == "replace" and ((a, b) in CONFUSIONS or (a, b) in MULTI_SET):
            out.append(b)
        else:
            out.append(a)                        # a real difference: keep the edition's reading
    return "".join(out)


def tokens(text):
    """[(start, end, word)]"""
    return [(m.start(), m.end(), m.group()) for m in TOKEN.finditer(text)]


def align(a, b, chunk=4000):
    """Pairs (i, j) of indexes of words in a and b that match (fold-equal),
    in order. Matching blocks from difflib over the folded sequences, in
    overlapping windows to keep it fast."""
    fa, fb = [fold(x) for x in a], [fold(x) for x in b]
    pairs = []
    i = j = 0
    while i < len(fa) and j < len(fb):
        wa, wb = fa[i:i + chunk], fb[j:j + int(chunk * 1.15)]
        sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
        blocks = [m for m in sm.get_matching_blocks() if m.size]
        if not blocks:
            i += chunk // 2
            continue
        # keep the matches in the first 80% of the window, then move on from the last one kept
        limit = int(len(wa) * 0.8) if i + chunk < len(fa) else len(wa)
        last = None
        for m in blocks:
            for k in range(m.size):
                if m.a + k < limit:
                    pairs.append((i + m.a + k, j + m.b + k))
                    last = (m.a + k, m.b + k)
        if last is None:
            i += chunk // 2
            continue
        i, j = i + last[0] + 1, j + last[1] + 1
    return pairs


def fuzzy_pairs(a, b, pairs, max_ratio=0.34):
    """Between two matched words, pair up the unmatched words of a and b that
    are close (one or two OCR errors): [(i, j)]."""
    out = []
    bounds = [(-1, -1)] + pairs + [(len(a), len(b))]
    for (i0, j0), (i1, j1) in zip(bounds, bounds[1:]):
        ga, gb = list(range(i0 + 1, i1)), list(range(j0 + 1, j1))
        if not ga or not gb or len(ga) > 12 or len(gb) > 12:
            continue
        used = set()
        for i in ga:
            fi = fold(a[i])
            best = None
            for j in gb:
                if j in used:
                    continue
                fj = fold(b[j])
                d = 1 - difflib.SequenceMatcher(None, fi, fj, autojunk=False).ratio()
                if d <= max_ratio and (best is None or d < best[0]):
                    best = (d, j)
            if best:
                used.add(best[1])
                out.append((i, best[1]))
    return sorted(out)


class Vocabulary:
    """Words seen in clean text, by their folded form: for repairing words
    the witness does not cover."""

    def __init__(self):
        self.by_fold = defaultdict(Counter)

    def add(self, words, weight=1):
        for w in words:
            if w and not re.search(r"\d", w):
                self.by_fold[fold(w)][w] += weight

    def variants(self, ocr):
        """The OCR word with one misreading undone, each way it could be."""
        yield ocr
        for a, b in MULTI:
            start = 0
            while True:
                i = ocr.find(a, start)
                if i < 0:
                    break
                yield ocr[:i] + b + ocr[i + len(a):]
                start = i + 1

    def best(self, ocr, min_count=2):
        """The most frequent known word the OCR word could be a misreading of
        (no more than one misreading of more than one letter)."""
        if ocr in self.by_fold.get(fold(ocr), {}):
            return ocr
        scored = Counter()
        for k, v in enumerate(self.variants(ocr)):
            for w, n in self.by_fold.get(fold(v), {}).items():
                if n >= min_count or k == 0:
                    scored[w] = max(scored[w], n * (3 if k == 0 else 1))
        return scored.most_common(1)[0][0] if scored else None
