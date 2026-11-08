"""Greek string helpers shared by the build pipeline.

Three levels of normalisation are used:
  lex_key(s)  - key for lexicon lookup: accents kept, grave->acute, quantity
                marks/digits/punctuation removed, lowercase.
  bare(s)     - no diacritics at all, final sigma folded: fallback lookup key
                and the key used to align treebank tokens with reading text.
"""
import re
import unicodedata

GRAVE, ACUTE = "\u0300", "\u0301"
QUANTITY = {"\u0304", "\u0306"}  # macron, breve
ELISION = "\u02bc\u2019'\u1fbd"  # modifier apostrophe, right quote, apostrophe, koronis

# A Greek word: letters + combining marks, optionally with an elision mark.
WORD_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF\u0300-\u036F]+[" + ELISION + r"]?")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def lex_key(s):
    s = unicodedata.normalize("NFD", s or "")
    out = []
    for ch in s:
        if ch in QUANTITY:
            continue
        if ch == GRAVE:
            ch = ACUTE
        if ch in ELISION:
            continue
        cat = unicodedata.category(ch)
        if cat[0] in "LM" and cat != "Lm":
            out.append(ch)
    s = unicodedata.normalize("NFC", "".join(out)).lower()
    return s.replace("ς", "σ")


def bare(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if ch not in ELISION)
    s = "".join(ch for ch in s if unicodedata.category(ch) in ("Lu", "Ll", "Lo"))
    return s.lower().replace("ς", "σ")


def tokenize(text):
    """Yield (start, end, form) for each Greek word in text."""
    for m in WORD_RE.finditer(text):
        yield m.start(), m.end(), m.group(0)


# AGDT 9-position postag -> readable parse
POS = dict(n="noun", v="verb", t="participle", a="adjective", d="adverb", l="article",
           g="particle", c="conjunction", r="preposition", p="pronoun", m="numeral",
           i="interjection", e="exclamation", u="punctuation", x="irregular")
FIELDS = [
    None,
    dict(zip("123", ["1st", "2nd", "3rd"])),
    dict(s="sg", p="pl", d="dual"),
    dict(p="pres", i="impf", r="perf", l="plup", t="futperf", f="fut", a="aor"),
    dict(i="ind", s="subj", o="opt", n="inf", m="imperat", p="part"),
    dict(a="act", p="pass", m="mid", e="mp"),
    dict(m="masc", f="fem", n="neut", c="common"),
    dict(n="nom", g="gen", d="dat", a="acc", v="voc", l="loc"),
    dict(c="comp", s="superl"),
]


def describe_postag(tag):
    if not tag or len(tag) < 9:
        return ""
    parts = [POS.get(tag[0], tag[0])]
    for i in range(1, 9):
        v = FIELDS[i].get(tag[i])
        if v:
            parts.append(v)
    return " ".join(parts)


def compound_lemma(form, part2_form, part2_lemma):
    """Lemma for a word the treebank split in two, rebuilt from the written
    form: οὐδʼ (+ δέ) -> οὐδέ ; οὔτʼ (+ τε) -> οὔτε ; οὐδὲ -> οὐδέ."""
    base = unicodedata.normalize("NFD", form.rstrip(ELISION)).replace(GRAVE, ACUTE)
    base = nfc(base)
    lem = nfc(re.sub(r"\d+$", "", part2_lemma or ""))
    lem_letters = [i for i, ch in enumerate(lem) if unicodedata.category(ch)[0] == "L"]
    n = len(bare(part2_form))
    tail = lem[lem_letters[n]:] if n < len(lem_letters) else ""
    return nfc(base + tail)


# ---------------------------------------------------------------- Beta Code --
# Morpheus speaks Beta Code (a)/eide = ἄειδε, *)axilleu/s = Ἀχιλλεύς).

_LETTERS = "αβγδεζηθικλμνξοπρστυφχψως"
_BETA = "abgdezhqiklmncoprstufxyws"
TO_BETA = dict(zip(_LETTERS, _BETA))
FROM_BETA = {b: g for g, b in zip(_LETTERS, _BETA) if g != "ς"}
MARK_TO_BETA = {"̓": ")", "̔": "(", "̈": "+", "́": "/", "̀": "\\",
                "͂": "=", "ͅ": "|"}
BETA_TO_MARK = {v: k for k, v in MARK_TO_BETA.items()}
_MARK_ORDER = ")(+/\\=|"


def to_beta(word):
    """Unicode Greek word -> Beta Code (capitals as *, elision as ')."""
    out = []
    for ch in unicodedata.normalize("NFD", word):
        if ch in ELISION:
            out.append("'")
            continue
        low = ch.lower()
        if low in TO_BETA:
            out.append(["*" if ch != low else "", TO_BETA[low], ""])
        elif ch in MARK_TO_BETA and out and isinstance(out[-1], list):
            out[-1][2] += MARK_TO_BETA[ch]
    result = []
    for item in out:
        if isinstance(item, str):
            result.append(item)
            continue
        star, letter, marks = item
        marks = "".join(sorted(marks, key=_MARK_ORDER.index))
        # capitals put their diacritics before the letter: *)/a
        result.append(star + marks + letter if star else letter + marks)
    return "".join(result)


QUANTITY = {"_": "\u0304", "^": "\u0306"}    # macron, breve (Autenrieth marks long vowels)


def from_beta(beta, quantity=False):
    """Beta Code -> Unicode. Homograph digits are dropped; so are quantity
    marks (a_ = ᾱ), unless `quantity` is set, for display."""
    beta = re.sub(r"\d" if quantity else r"[_^\d]", "", beta)
    out, i = [], 0
    while i < len(beta):
        ch = beta[i]
        if ch == "*":
            j = i + 1
            marks = ""
            while j < len(beta) and beta[j] in BETA_TO_MARK:
                marks += beta[j]
                j += 1
            if j < len(beta) and beta[j].lower() in FROM_BETA:
                out.append(FROM_BETA[beta[j].lower()].upper() + "".join(BETA_TO_MARK[m] for m in marks))
                i = j + 1
                continue
            i += 1
            continue
        if ch.lower() in FROM_BETA:
            out.append(FROM_BETA[ch.lower()])
        elif ch in BETA_TO_MARK and out:
            out[-1] += BETA_TO_MARK[ch]
        elif quantity and ch in QUANTITY and out:
            out[-1] += QUANTITY[ch]
        elif ch == "'":
            out.append("ʼ")
        i += 1
    s = "".join(out)
    s = re.sub(r"σ(?=$|[^\ẁ-ͯ])", "ς", s)
    return unicodedata.normalize("NFC", s)
