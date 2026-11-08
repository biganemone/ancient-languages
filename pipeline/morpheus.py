"""Morphological analyses from Morpheus for words without treebank data.

Morpheus runs only at build time (it never ships in the app). Results are
kept in a cache (pipeline/data/morpheus_cache.tsv.gz, committed), so a build
needs the Morpheus binary only when new words appear.

  MORPHEUS=/path/to/morpheus  (a checkout of perseids-tools/morpheus with
  bin/cruncher and a built stemlib/) enables running it.

Morpheus lists every possible analysis, not the one meant in context; the
app shows them as a short ranked list.
"""
import gzip
import os
import re
import subprocess

import greek

CACHE = os.path.join(os.path.dirname(__file__), "data", "morpheus_cache.tsv.gz")

ABBREV = {
    "pres": "present", "imperf": "imperfect", "fut": "future", "aor": "aorist",
    "perf": "perfect", "plup": "pluperfect", "futperf": "future perfect",
    "ind": "indicative", "subj": "subjunctive", "opt": "optative", "inf": "infinitive",
    "imperat": "imperative", "part": "participle",
    "act": "active", "mid": "middle", "pass": "passive", "mp": "middle-passive",
    "masc": "masculine", "fem": "feminine", "neut": "neuter",
    "nom": "nominative", "gen": "genitive", "dat": "dative", "acc": "accusative", "voc": "vocative",
    "sg": "singular", "pl": "plural", "dual": "dual",
    "1st": "1st person", "2nd": "2nd person", "3rd": "3rd person",
    "comp": "comparative", "superl": "superlative", "adverbial": "adverb",
}
INDECLINABLE = {"particle": "particle", "prep": "preposition", "article": "article",
                "adverb": "adverb", "conj": "conjunction", "exclam": "interjection",
                "numeral": "numeral"}

NL = re.compile(r"<NL>(.*?)</NL>")


def describe(pos, features, stemtype):
    words = [ABBREV.get(w, w) for w in re.split(r"\s+", features.strip()) if w]
    words = ["/".join(ABBREV.get(p, p) for p in w.split("/")) for w in words]
    kind = next((v for k, v in INDECLINABLE.items() if k in stemtype.split(",")), None)
    if pos == "V":
        head = "participle" if "participle" in words else "verb"
        words = [w for w in words if w != "participle"]
    elif pos == "P":
        head = "participle"
        words = [w for w in words if w != "participle"]
    else:
        if not kind and "pron" in stemtype:
            kind = "pronoun"
        head = kind or ("adverb" if "adverb" in words else "noun/adjective")
        words = [w for w in words if w != "adverb"]
    return " · ".join([head] + words)


def parse_output(text):
    """cruncher output -> {beta form: [(lemma, parse, dialects), ...]}"""
    result, form = {}, None
    for line in text.splitlines():
        if line.startswith(":") or not line.strip():
            continue
        if line.startswith("<NL>"):
            if form is None:
                continue
            for body in NL.findall(line):
                m = re.match(r"(\w) +(\S+) *([^\t]*)\t([^\t]*)\t([^\t]*)\t?(.*)", body)
                if not m:
                    continue
                pos, lemmas, features, dialects, _notes, stemtype = m.groups()
                lemma = greek.from_beta(lemmas.split(",")[-1])
                result.setdefault(form, []).append(
                    (lemma, describe(pos, features, stemtype), dialects.strip()))
        else:
            form = line.strip()
            result.setdefault(form, [])
    return result


def run(forms, morpheus_dir):
    """Analyse Beta Code forms with cruncher (-S: allow capitals)."""
    env = dict(os.environ, MORPHLIB=os.path.join(morpheus_dir, "stemlib"))
    out = subprocess.run([os.path.join(morpheus_dir, "bin", "cruncher"), "-S"],
                         input="\n".join(forms) + "\n", capture_output=True, text=True, env=env)
    return parse_output(out.stdout)


def load_cache():
    cache = {}
    if os.path.exists(CACHE):
        with gzip.open(CACHE, "rt", encoding="utf-8") as f:
            for line in f:
                beta, lemma, parse, dialects = (line.rstrip("\n").split("\t") + ["", "", ""])[:4]
                entry = cache.setdefault(beta, [])
                if lemma:
                    entry.append((lemma, parse, dialects))
    return cache


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with gzip.open(CACHE, "wt", encoding="utf-8", compresslevel=9) as f:
        for beta in sorted(cache):
            rows = cache[beta] or [("", "", "")]
            for lemma, parse, dialects in rows:
                f.write(f"{beta}\t{lemma}\t{parse}\t{dialects}\n")


def analyses(words, dialect, frequency=None):
    """{unicode form: [(lemma, parse)] ranked}, using the cache and Morpheus
    if available. Ranking: analyses with no dialect restriction, then the
    work's dialect ('epic' or 'attic'), then others; within that, lemmas that
    are common in the treebanks (`frequency`: lemma key -> count) first."""
    frequency = frequency or {}
    cache = load_cache()
    betas = {w: greek.to_beta(w) for w in words}
    missing = sorted({b for b in betas.values() if b not in cache})
    morpheus_dir = os.environ.get("MORPHEUS")
    if missing and morpheus_dir:
        found = run(missing, morpheus_dir)
        for b in missing:
            cache[b] = found.get(b, [])
        save_cache(cache)
    elif missing:
        print(f"note: {len(missing)} forms not in the Morpheus cache and MORPHEUS is not set")

    def rank(row):
        lemma, parse, dialects = row
        d = 0 if (not dialects or dialect in dialects) else 1
        # rarer readings of the same form go later (duals; the -ει 2nd sg middle)
        rare = ("dual" in parse) + ("2nd person · singular" in parse and "middle-passive" in parse)
        return (d, -frequency.get(greek.lex_key(lemma), 0), rare)

    out = {}
    for word, beta in betas.items():
        rows = sorted(cache.get(beta, []), key=rank)
        seen, ranked = set(), []
        for lemma, parse, _d in rows:
            if (lemma, parse) not in seen:
                seen.add((lemma, parse))
                ranked.append((lemma, parse))
        out[word] = ranked
    return out


# ------------------------------------------------------------------ Latin --
LATIN_CACHE = os.path.join(os.path.dirname(__file__), "data", "morpheus_latin_cache.tsv.gz")
LATIN_ABBREV = {"abl": "ablative", "loc": "locative", "gerundive": "gerundive", "supine": "supine",
                "futperf": "future perfect", "plupf": "pluperfect", "dep": "deponent"}


def parse_latin_output(text):
    """cruncher -L output -> {form: [(lemma, parse), ...]}. Lemmas keep
    Morpheus's homograph number as a digit ('dico#2' -> 'dico2'); macron
    marks are dropped."""
    result, form = {}, None
    for line in text.splitlines():
        if line.startswith(":") or not line.strip():
            continue
        if line.startswith("<NL>"):
            if form is None:
                continue
            for body in NL.findall(line):
                m = re.match(r"(\w) +(\S+) *([^\t]*)\t([^\t]*)\t([^\t]*)\t?(.*)", body)
                if not m:
                    continue
                pos, lemmas, features, dialects, notes, stemtype = m.groups()
                dialects = " ".join(x for x in (dialects.strip(), notes.strip()) if x in
                                    ("poetic", "early", "late", "archaic", "rare"))
                lemma = lemmas.split(",")[-1].replace("_", "").replace("^", "").replace("#", "")
                words = [LATIN_ABBREV.get(w, w) for w in features.split()]
                parse = describe(pos, " ".join(words), stemtype)
                if dialects.strip():                     # "poetic", "early", …: rarer readings
                    parse += " · " + dialects.strip()
                result.setdefault(form, []).append((lemma, parse))
        else:
            form = line.strip()
            result.setdefault(form, [])
    return result


def _load_latin():
    cache = {}
    if os.path.exists(LATIN_CACHE):
        with gzip.open(LATIN_CACHE, "rt", encoding="utf-8") as f:
            for line in f:
                form, lemma, parse = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                entry = cache.setdefault(form, [])
                if lemma:
                    entry.append((lemma, parse))
    return cache


def _save_latin(cache):
    with gzip.open(LATIN_CACHE, "wt", encoding="utf-8", compresslevel=9) as f:
        for form in sorted(cache):
            for lemma, parse in cache[form] or [("", "")]:
                f.write(f"{form}\t{lemma}\t{parse}\n")


def latin_analyses(words, frequency=None):
    """{form: [(lemma, parse)] ranked} for Latin words: Morpheus (-L) through
    its own cache, ranked by how common each lemma is in the Latin treebanks
    (`frequency`: latin.key(lemma) -> count)."""
    import latin
    frequency = frequency or {}
    cache = _load_latin()
    inputs = {w: latin.morpheus_form(w) for w in words}
    missing = sorted({f for f in inputs.values() if f not in cache})
    morpheus_dir = os.environ.get("MORPHEUS")
    if missing and morpheus_dir:
        env = dict(os.environ, MORPHLIB=os.path.join(morpheus_dir, "stemlib"))
        found = {}
        query = sorted(set(missing) | {f.lower() for f in missing})
        for i in range(0, len(query), 20000):
            out = subprocess.run([os.path.join(morpheus_dir, "bin", "cruncher"), "-L"],
                                 input="\n".join(query[i:i + 20000]) + "\n", capture_output=True,
                                 text=True, env=env)
            found.update(parse_latin_output(out.stdout))
        for f in missing:
            cache[f] = found.get(f, [])
            if not cache[f] and f[:1].isupper():          # sentence-initial capital
                cache[f] = found.get(f.lower(), [])
        _save_latin(cache)
    elif missing:
        import sys
        print(f"note: {len(missing)} Latin forms not in the Morpheus cache and MORPHEUS is not set",
              file=sys.stderr)

    out = {}
    for word, f in inputs.items():
        rows = cache.get(f) or cache.get(f.lower()) or []
        rows = sorted(rows, key=lambda r: ("·" in r[1] and r[1].split(" · ")[-1] in ("poetic", "early", "late", "archaic"),
                                           -frequency.get(latin.key(r[0]), 0)))
        seen, ranked = set(), []
        for lemma, parse in rows:
            if (lemma, parse) not in seen:
                seen.add((lemma, parse))
                ranked.append((lemma, parse))
        out[word] = ranked
    return out
