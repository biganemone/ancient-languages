"""Latin text helpers: lookup keys, the tokenizer, and treebank/PROIEL tags.

Lookup keys ignore the spelling variation between editions and dictionaries:
case, macrons and breves, æ/œ ligatures, diaeresis, and i/j and u/v
(Clementine "ejus", "cælum"; Lewis & Short "eius", "caelum"; Morpheus "jam").
"""
import re
import unicodedata

WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-žǢǣȲȳḗ-ỿ]+(?:['’][A-Za-z]+)?")
LETTER_KEYS = str.maketrans({"j": "i", "v": "u", "æ": "ae", "œ": "oe"})


def strip_marks(s):
    s = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(c for c in s if not unicodedata.combining(c)))


def key(word):
    """'Cælum' -> 'caelum', 'ejus' -> 'eius', 'virumque' -> 'uirumque'.
    Homograph numbers (Lewis & Short's 'lego2', Morpheus's 'dico#2', the
    treebank's 'sic1') are dropped."""
    w = strip_marks(word or "").lower().replace("_", "").replace("^", "").replace("-", "")
    w = re.sub(r"[#]?\d+$", "", w)
    return w.translate(LETTER_KEYS)


def bare(word):
    return key(word)


def morpheus_form(word):
    """The spelling Morpheus expects: no ligatures or marks (it handles j/v itself)."""
    w = strip_marks(word).replace("æ", "ae").replace("Æ", "Ae").replace("œ", "oe").replace("Œ", "Oe")
    return w


def is_latin(k):
    return bool(k) and k[0].isascii() and k[0].isalpha()


def tokenize(text):
    """[(start, end, form)] for each Latin word (character offsets)."""
    return [(m.start(), m.end(), m.group()) for m in WORD.finditer(text)]


# PROIEL part of speech -> AGDT first letter
PROIEL_POS = {"V-": "v", "Nb": "n", "Ne": "n", "A-": "a", "Df": "d", "Dq": "d", "Du": "d",
              "C-": "c", "G-": "c", "R-": "r", "S-": "l", "Ma": "m", "Mo": "m", "I-": "i",
              "Pp": "p", "Pd": "p", "Pr": "p", "Pi": "p", "Px": "p", "Ps": "p", "Pk": "p",
              "Pc": "p", "Pt": "p", "F-": "x", "X-": "x"}


def proiel_postag(pos, morph):
    """PROIEL part of speech + morphology ("3suia----i") -> AGDT 9-character tag.
    PROIEL's first eight places (person, number, tense, mood, voice, gender,
    case, degree) are the AGDT's 2nd–9th; combined values (gender 'o', case
    'c') become '-'."""
    m = (morph or "-" * 10).ljust(10, "-")
    person, number, tense, mood, voice, gender, case, degree = m[:8]
    tense = {"p": "p", "i": "i", "r": "r", "l": "l", "t": "t", "f": "f", "a": "a", "s": "r"}.get(tense, "-")
    mood = {"i": "i", "s": "s", "m": "m", "o": "o", "n": "n", "p": "p", "d": "d", "g": "g", "u": "u"}.get(mood, "-")
    voice = {"a": "a", "p": "p", "m": "m", "e": "e"}.get(voice, "-")
    gender = gender if gender in "mfn" else "-"
    case = case if case in "nagdbvl" else "-"
    degree = {"c": "c", "s": "s"}.get(degree, "-")
    number = number if number in "spd" else "-"
    person = person if person in "123" else "-"
    return PROIEL_POS.get(pos, "-") + person + number + tense + mood + voice + gender + case + degree
