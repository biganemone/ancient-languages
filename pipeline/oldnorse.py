"""Old Norse helpers: lookup keys and the tokenizer.

Keys. Old Norse lemma keys carry a prefix, "non:", because plain Latin
letters would otherwise collide with Latin lemma keys in the shared lemma and
short-definition tables (and an unprefixed key that starts with an ASCII
letter is taken for Latin: latin.is_latin). Inside the prefix the spelling is
folded so that the editions' spellings and the dictionaries' meet:

  - lowercase, NFC;
  - ǫ, ö, ø written ö (Pettit and the Altnordische Saga-Bibliothek print ǫ,
    the 1907 Edda and Zoëga ö); œ written æ;
  - accents kept (they tell words apart: á "on", a "has");
  - no hyphens.
"""
import re
import unicodedata

PREFIX = "non:"
LETTERS = "A-Za-zÁÉÍÓÚÝÞÐÆÖØǪŒáéíóúýþðæöøǫœ"
WORD = re.compile(rf"[{LETTERS}](?:[{LETTERS}]|-(?=[{LETTERS}]))*")


def tokenize(text):
    """[(start, end, form)] for each word (character offsets); hyphenated
    names stay whole ("orms-í-auga")."""
    return [(m.start(), m.end(), m.group()) for m in WORD.finditer(text)]


def fold(word):
    w = unicodedata.normalize("NFC", (word or "").lower())
    w = w.replace("ǫ", "ö").replace("ø", "ö").replace("œ", "æ").replace("-", "")
    return w


def key(word):
    """The lookup key of a headword or form: 'Mǫrðr' -> 'non:mörðr'."""
    return PREFIX + fold(word)


def is_old_norse(k):
    return bool(k) and k.startswith(PREFIX)


def strip_accents(s):
    d = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(c for c in d if not unicodedata.combining(c)))
