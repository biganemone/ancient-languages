"""Old English word forms -> possible lemmas and parses, for texts without a
glossary of their own (everything but Beowulf).

Readings come from two places:

  1. Beowulf, as analysed from Klaeber's glossary (oldenglish.py): a form seen
     there gets the lemma (and parse) it had there, ranked first.
  2. Ondřej Tichý's morphological generator for Old English (CC BY 4.0;
     madeleineth/tichy_oe_generator), which inflects every Bosworth–Toller
     headword: some 14 million generated forms. `data/oe_forms.tsv.gz` keeps
     the readings of the forms that occur in our texts (regenerate with
     `python oe_forms.py extract <generator output.txt> <ASPR html dir>`).

Ambiguous forms keep all their readings (shown as "possible parses"). The
order is decided by lemma frequency, estimated over the whole corpus by a few
rounds of EM: each token shares itself among its candidate lemmas in
proportion to how common each lemma is overall.

  python oe_forms.py extract <output.txt> <aspr html dir>     # refresh data/oe_forms.tsv.gz
"""
import gzip
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import oldenglish as oe

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "data", "oe_forms.tsv.gz")

# (the generator's headwords use capital accented vowels inside words, "beÓn", for an uncertain length)
ACUTE_TO_MACRON = str.maketrans({"á": "ā", "é": "ē", "í": "ī", "ó": "ō", "ú": "ū", "ý": "ȳ", "ǽ": "ǣ",
                                 "Á": "ā", "É": "ē", "Í": "ī", "Ó": "o", "Ú": "u", "Ý": "y", "Ǽ": "ǣ"})


def norm(word):
    """Tichý's spelling: no marks, lowercase, ð as þ, y as i (cyning -> cining)."""
    w = oe.form_key(word)
    return w.replace("y", "i")


def bt_display(hw):
    """Bosworth–Toller marks long vowels with acutes; show macrons, as Klaeber does."""
    hw = unicodedata.normalize("NFC", hw)
    return hw[:1] + hw[1:].translate(ACUTE_TO_MACRON) if hw[:1].isupper() else hw.translate(ACUTE_TO_MACRON)


# Common words whose spellings in the poetry the form tables lack (Klaeber
# writes "oð þæt" as two words; Bosworth–Toller's headwords are West Saxon).
EXTRA = {"oþþæt": ("oþ-þæt", "c--------"), "oþþe": ("oþþe", "c--------"), "forþæm": ("for-þǣm", "c--------"),
         "forþon": ("for-þon", "c--------"), "forþan": ("for-þon", "c--------"),
         "sindan": ("eom", "v--pi----"), "sindon": ("eom", "v--pi----"), "syndon": ("eom", "v--pi----"),
         "sint": ("eom", "v--pi----"), "wærun": ("eom", "v-pei----"), "usser": ("ic", "p-p----g-"),
         "usses": ("ic", "p-p----g-"), "teala": ("tela", "d--------"), "tela": ("tela", "d--------")}

# One-letter spelling variants between dialects and editions (and/ond,
# meotud/meotod, woruld/weoruld, silf/self, simle/symle), tried when a form
# has no reading as written.
VARIANTS = [("and", "ond"), ("ond", "and"), ("an", "on"), ("on", "an"), ("am", "om"), ("om", "am"),
            ("io", "eo"), ("eo", "io"), ("ie", "i"), ("i", "ie"), ("i", "e"), ("e", "i"), ("u", "o"), ("o", "u"),
            ("o", "eo"), ("eo", "e"), ("ea", "a"), ("a", "ea"), ("æ", "e"), ("e", "æ"), ("æ", "ea"), ("c", "cc"),
            ("g", "gg"), ("ll", "l"), ("l", "ll"), ("nn", "n"), ("n", "nn"), ("tt", "t"), ("dd", "d"), ("h", "")]


def variants(k):
    out = []
    for a, b in VARIANTS:
        i = k.find(a)
        while i != -1:
            v = k[:i] + b + k[i + len(a):]
            if v != k and v not in out:
                out.append(v)
            i = k.find(a, i + 1)
    return out


# ------------------------------------------------------------- parse codes --
CASES = {"no": "n", "ac": "a", "ge": "g", "da": "d", "in": "i", "is": "i"}
GENDERS = {"ma": "m", "fe": "f", "ne": "n"}
NUMBERS = {"sg": "s", "pl": "p", "du": "d"}
POS_WORDS = {"noun": "n", "adjective": "a", "participle": "t", "verb": "v", "pronoun": "p", "adverb": "d",
             "numeral": "m", "preposition": "r", "conjunction": "c", "interjection": "i"}


def tag_from_code(code, pos, tense_word=None):
    """Tichý's codes ('SgMaNo', 'PoPlFeDa', 'PsInSg3', 'IdIf', 'painsg1') ->
    a 9-character AGDT-style tag (tense 'e' = past, case 'i' = instrumental)."""
    c = re.sub(r"\d+$", "", (code or "").lower())
    p = POS_WORDS.get(pos, "-")
    person = number = tense = mood = gender = case = degree = "-"
    if p in ("v", "t") or re.match(r"^(ps|pa|im|if|idif|inf|pp|pspa|impsg)", c):
        m = re.match(r"^(ps|pa)?(in|su|sj)?(sg|pl)?([123])?$", c)
        if c in ("if", "inf"):
            p, mood = "v", "n"
        elif c == "idif":
            p, mood = "v", "d"
        elif c in ("pspt", "papt", "pp", "pspa"):
            p, mood, tense = "t", "p", "p" if c in ("pspt", "pspa") else "e"
        elif c.startswith("im"):
            p, mood = "v", "m"
            number = "p" if c.endswith("pl") else "s"
        elif m:
            p = "v"
            tense = {"ps": "p", "pa": "e"}.get(m.group(1), "-")
            mood = {"in": "i", "su": "s", "sj": "s"}.get(m.group(2), "-")
            number = NUMBERS.get(m.group(3), "-")
            person = m.group(4) or "-"
        if p == "t" and pos == "participle":
            tense = "p" if tense_word == "present" else "e" if tense_word == "past" else tense
            mood = "p"
        if pos == "participle" and c[:2] in ("po", "co", "sp"):
            degree = {"po": "-", "co": "c", "sp": "s"}[c[:2]]
            rest = c[2:]
            number, gender, case = NUMBERS.get(rest[:2], "-"), GENDERS.get(rest[2:4], "-"), CASES.get(rest[4:6], "-")
            p, mood = "t", "p"
            tense = "p" if tense_word == "present" else "e"
    else:
        rest = c
        if rest[:2] in ("po", "co", "sp", "su") and p in ("a", "d", "-", "m"):
            degree = {"po": "-", "co": "c", "sp": "s", "su": "s"}[rest[:2]]
            rest = rest[2:]
        if rest[:2] in NUMBERS:
            number = NUMBERS[rest[:2]]
            rest = rest[2:]
        if rest[:2] in GENDERS:
            gender = GENDERS[rest[:2]]
            rest = rest[2:]
        if rest[:2] in CASES:
            case = CASES[rest[:2]]
    return p + person + number + tense + mood + "-" + gender + case + degree


PARSE_WORDS = [
    {"n": "noun", "v": "verb", "t": "participle", "a": "adjective", "d": "adverb", "l": "article",
     "g": "particle", "c": "conjunction", "r": "preposition", "p": "pronoun", "m": "numeral",
     "i": "interjection"},
    {"1": "1st person", "2": "2nd person", "3": "3rd person"},
    {"s": "singular", "p": "plural", "d": "dual"},
    {"p": "present", "e": "past"},
    {"i": "indicative", "s": "subjunctive", "o": "optative", "n": "infinitive", "m": "imperative",
     "p": "participle", "d": "inflected infinitive"},
    {},
    {"m": "masculine", "f": "feminine", "n": "neuter"},
    {"n": "nominative", "g": "genitive", "d": "dative", "a": "accusative", "i": "instrumental", "v": "vocative"},
    {"c": "comparative", "s": "superlative"},
]


def describe(tag):
    """A parse as the app writes it: 'noun · singular · masculine · dative'."""
    if not tag or len(tag) < 9:
        return ""
    out = []
    for i, ch in enumerate(tag[:9]):
        word = PARSE_WORDS[i].get(ch)
        if word and not (tag[0] == "t" and i == 4):
            out.append(word)
    return " · ".join(out)


# ------------------------------------------------------------------ tables --
def load_table(path=TABLE):
    """{norm form: [(lemma display, lemma key, tag)]}"""
    out = defaultdict(list)
    if not os.path.exists(path):
        return out
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            form, hw, pos, code, tense = (line.rstrip("\n").split("\t") + [""] * 5)[:5]
            tag = tag_from_code(code, pos, tense)
            row = (bt_display(hw), oe.PREFIX + oe.form_key(hw), tag)
            if row not in out[form]:
                out[form].append(row)
    return out


class Analyser:
    """Readings for each written form, ranked."""

    def __init__(self, beowulf_readings, table=None):
        """beowulf_readings: {form_key: Counter((lemma display, key, tag))}."""
        self.beowulf = beowulf_readings
        self.table = table if table is not None else load_table()
        self.weight = Counter()

    def candidates(self, word):
        fk, nk = oe.form_key(word), norm(word)
        out = []
        found = self.beowulf.get(fk)
        if not found and fk not in EXTRA:
            found = next((self.beowulf[v] for v in variants(fk) if v in self.beowulf), None)
        for (lemma, key, tag), n in (found or Counter()).most_common():
            out.append((lemma, key, tag, "beowulf"))
        if fk in EXTRA:
            hw, tag = EXTRA[fk]
            out.append((hw, oe.PREFIX + oe.form_key(hw), tag, "beowulf"))
        rows = self.table.get(nk) or []
        if not rows and not out:
            for v in ([nk[2:]] if nk.startswith("ge") and len(nk) > 4 else []) + variants(nk):
                rows = self.table.get(v) or []
                if rows:
                    break
        for lemma, key, tag in rows:
            out.append((lemma, key, tag, "tichy"))
        return out

    def train(self, words, rounds=4):
        """Lemma weights by EM over all tokens (Beowulf's lemmas as a prior)."""
        cands = [self.candidates(w) for w in words]
        prior = Counter()
        for c in self.beowulf.values():
            for (lemma, key, tag), n in c.items():
                prior[key] += n
        weight = Counter({k: v + 1 for k, v in prior.items()})
        for _ in range(rounds):
            new = Counter(prior)
            for cs in cands:
                keys = {c[1] for c in cs}
                if not keys:
                    continue
                total = sum(weight[k] or 0.5 for k in keys)
                for k in keys:
                    new[k] += (weight[k] or 0.5) / total
            weight = new
        self.weight = weight

    def readings(self, word, limit=8):
        """[(lemma, key, tag)] most likely first; Beowulf's own reading of the
        form leads when it has one."""
        cs = self.candidates(word)
        if not cs:
            return []
        seen, ranked = set(), []
        def likely(c):
            # imperatives are rare in the verse; a noun's form that is also an
            # imperative of a derived verb (swefna, treow) is nearly always the noun
            w = self.weight[c[1]] * (0.2 if (c[2] or "")[:1] == "v" and (c[2] or "")[4:5] == "m" else 1)
            return (c[3] != "beowulf", -w, "-" in c[0], len(c[0]))
        for lemma, key, tag, src in sorted(cs, key=likely):
            sig = (key, tag)
            if sig in seen:
                continue
            seen.add(sig)
            ranked.append((lemma, key, tag))
        # one lemma's readings together, in the order the lemmas first appear
        order = list(dict.fromkeys(r[1] for r in ranked))
        ranked.sort(key=lambda r: order.index(r[1]))
        return ranked[:limit]


# ----------------------------------------------------------------- extract --
def extract(generator_output, html_dir):
    import aspr
    forms = set()
    for poem in aspr.read_corpus(html_dir):
        for _, text in poem["lines"]:
            for _, _, w in oe.tokenize(text):
                nk = norm(w)
                forms.add(nk)
                if nk.startswith("ge"):
                    forms.add(nk[2:])
                forms.update(variants(nk))
    kept = 0
    os.makedirs(os.path.dirname(TABLE), exist_ok=True)
    with open(generator_output, encoding="utf-8", errors="replace") as f, \
            gzip.open(TABLE, "wt", encoding="utf-8") as out:
        out.write("# Old English forms occurring in our texts, with their readings from Ondřej Tichý's "
                  "morphological generator (CC BY 4.0; github.com/madeleineth/tichy_oe_generator).\n"
                  "# form (normalised)\tBosworth–Toller headword\tpart of speech\tcode\tparticiple tense\n")
        seen = set()
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 10:
                continue
            form = norm(cols[1])
            if form not in forms:
                continue
            pos = next((c for c in cols[10:] if c in POS_WORDS), "")
            tense = next((c for c in cols[10:] if c in ("present", "past")), "")
            row = (form, cols[3], pos, cols[9], tense)
            if row in seen:
                continue
            seen.add(row)
            out.write("\t".join(row) + "\n")
            kept += 1
    print(f"{len(forms)} corpus forms; {kept} readings kept -> {TABLE}", file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1] == "extract":
        extract(sys.argv[2], sys.argv[3])
