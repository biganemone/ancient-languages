"""Hebrew helpers: the Open Scriptures Hebrew Bible's morphology codes
(https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html), lemma
keys, and the prefixes it marks with letters.

A word's morph code is a language letter (H Hebrew, A Aramaic) and then one
segment per morpheme, separated by "/": prefixes (C conjunction, R
preposition, Td article…), the word itself, and suffixes (Sp3ms…). The lemma
has one segment per prefix and the word (suffixes have none): "c/b/7225".

Lemma keys are "heb:" + the augmented Strong's number ("heb:1254a"), or
"heb:" + the prefix letter ("heb:b"), so they never collide with other
languages' keys.
"""
import re
import unicodedata

PREFIX = "heb:"

# Prefix lemmas (letters) -> (headword, gloss)
PARTICLES = {
    "b": ("בְּ", "in, at, with, by"), "c": ("וְ", "and"), "d": ("הַ", "the"), "i": ("הֲ", "interrogative particle"),
    "k": ("כְּ", "like, as, according to"), "l": ("לְ", "to, for, belonging to"), "m": ("מִן", "from, out of, than"),
    "s": ("שֶׁ", "who, which, that"),
}

STEM_HE = {"q": "qal", "N": "niphal", "p": "piel", "P": "pual", "h": "hiphil", "H": "hophal", "t": "hithpael",
           "o": "polel", "O": "polal", "r": "hithpolel", "m": "poel", "M": "poal", "k": "palel", "K": "pulal",
           "Q": "qal passive", "l": "pilpel", "L": "polpal", "f": "hithpalpel", "D": "nithpael", "j": "pealal",
           "i": "pilel", "u": "hothpaal", "c": "tiphil", "v": "hishtaphel", "w": "nithpalel", "y": "nithpoel",
           "z": "hithpoel"}
STEM_AR = {"q": "peal", "Q": "peil", "u": "hithpeel", "p": "pael", "P": "ithpaal", "M": "hithpaal", "a": "aphel",
           "h": "haphel", "s": "saphel", "e": "shaphel", "H": "hophal", "i": "ithpeel", "t": "hishtaphel",
           "v": "ishtaphel", "w": "hithaphel", "o": "polel", "z": "ithpoel", "r": "hithpolel", "f": "hithpalpel",
           "b": "hephal", "c": "tiphel", "m": "poel", "l": "palpel", "L": "ithpalpel", "O": "ithpolel",
           "G": "ittaphal", "N": "niphal"}
CONJ = {"p": "perfect", "q": "sequential perfect", "i": "imperfect", "w": "sequential imperfect",
        "h": "cohortative", "j": "jussive", "v": "imperative", "r": "active participle",
        "s": "passive participle", "a": "infinitive absolute", "c": "infinitive construct"}
ADJ = {"a": "adjective", "c": "cardinal number", "g": "gentilic adjective", "o": "ordinal number"}
NOUN = {"c": "noun", "g": "gentilic noun", "p": "proper noun"}
PRON = {"d": "demonstrative pronoun", "f": "indefinite pronoun", "i": "interrogative pronoun",
        "p": "personal pronoun", "r": "relative pronoun"}
SUFF = {"d": "directional he", "h": "paragogic he", "n": "paragogic nun", "p": "pronominal suffix"}
PART = {"a": "particle of affirmation", "d": "definite article", "e": "particle of exhortation",
        "i": "interrogative particle", "j": "interjection", "m": "demonstrative particle", "n": "negative particle",
        "o": "direct object marker", "r": "relative particle"}
PERSON = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
GENDER = {"b": "common", "c": "common", "f": "feminine", "m": "masculine"}
NUMBER = {"d": "dual", "p": "plural", "s": "singular"}
STATE = {"a": "absolute", "c": "construct", "d": "determined"}


def segments(morph):
    """'HC/Vqw3ms' -> ('H', ['C', 'Vqw3ms'])"""
    lang, rest = morph[:1], morph[1:]
    return lang, rest.split("/")


def _pgn(s):
    out = []
    for ch, table in zip(s, (PERSON, GENDER, NUMBER, STATE)):
        if ch in table:
            out.append(table[ch])
    return out


def describe(seg, lang="H"):
    """One morpheme's code -> readable parse ('verb · qal · sequential imperfect
    · 3rd person · masculine · singular')."""
    if not seg:
        return ""
    pos, rest = seg[0], seg[1:]
    rest = rest.replace("x", " ")
    out = []
    if pos == "V":
        stems = STEM_AR if lang == "A" else STEM_HE
        out = ["verb", stems.get(rest[:1], rest[:1]), CONJ.get(rest[1:2], "")]
        tail = rest[2:]
        if rest[1:2] in "rs":           # participles: gender, number, state
            out += [GENDER.get(c) or NUMBER.get(c) or STATE.get(c) for c in tail if c != " "]
            out = [x for x in out if x]
        else:
            out += [x for x in (PERSON.get(tail[:1]), GENDER.get(tail[1:2]), NUMBER.get(tail[2:3])) if x]
    elif pos == "N":
        out = [NOUN.get(rest[:1], "noun")] + [x for x in (GENDER.get(rest[1:2]), NUMBER.get(rest[2:3]),
                                                          STATE.get(rest[3:4])) if x]
    elif pos == "A":
        out = [ADJ.get(rest[:1], "adjective")] + [x for x in (GENDER.get(rest[1:2]), NUMBER.get(rest[2:3]),
                                                              STATE.get(rest[3:4])) if x]
    elif pos == "P":
        out = [PRON.get(rest[:1], "pronoun")] + [x for x in (PERSON.get(rest[1:2]), GENDER.get(rest[2:3]),
                                                             NUMBER.get(rest[3:4])) if x]
    elif pos == "S":
        out = [SUFF.get(rest[:1], "suffix")] + [x for x in (PERSON.get(rest[1:2]), GENDER.get(rest[2:3]),
                                                            NUMBER.get(rest[3:4])) if x]
    elif pos == "T":
        out = [PART.get(rest[:1], "particle")]
    elif pos == "R":
        out = ["preposition"] + (["with the article"] if rest[:1] == "d" else [])
    elif pos == "C":
        out = ["conjunction"]
    elif pos == "D":
        out = ["adverb"]
    else:
        out = [seg]
    if lang == "A" and out:
        out.append("(Aramaic)")
    return " · ".join(x for x in out if x)


def agdt(seg):
    """A 9-character AGDT-style tag for the word's main morpheme (part of
    speech and, roughly, person/number/gender), for the function-word flag and
    sorting; the app shows the readable parse instead."""
    if not seg:
        return None
    pos = {"V": "v", "N": "n", "A": "a", "P": "p", "R": "r", "C": "c", "D": "d", "T": "g", "S": "p"}.get(seg[0], "-")
    if seg[:2] == "Td":
        pos = "l"
    if seg[:2] == "Np":
        pos = "n"
    return pos + "-" * 8


def main_index(morph_segments):
    """Which morpheme is the word: the first that is not a prefix (C, R, Td,
    Ti) or a suffix (S)."""
    for i, seg in enumerate(morph_segments):
        if seg[:1] in ("C", "R", "S") or seg[:2] in ("Td", "Ti"):
            continue
        return i
    # a word made only of a preposition and a suffix (אֲלֵיהֶם): the preposition
    for i, seg in enumerate(morph_segments):
        if seg[:1] != "S":
            return i
    return 0


def lemma_key(lemma):
    """'1254 a' -> 'heb:1254a'; 'b' -> 'heb:b'; '7225+' -> 'heb:7225'."""
    l = re.sub(r"[\s+]", "", lemma or "")
    return PREFIX + l if l else None


def is_hebrew_key(k):
    return bool(k) and k.startswith(PREFIX)


CANTILLATION = re.compile("[֑-ֽ֯׀׃׆]")


def plain(text):
    """Consonants only (no points or accents), for matching."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
