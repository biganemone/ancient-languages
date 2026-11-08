"""Which aorist forms are second (or otherwise irregular) aorists.

Flashcards give a second or irregular aorist (εἶπον, ἦλθον, ἔβην) its own
card. Neither the treebank nor our Morpheus cache says which aorists those
are, but Morpheus knows: each analysis carries a stem type ("aor1",
"aor2", "ath_h_aor" for root aorists like ἔβην, …).

This module keeps a small cache, data/morpheus_aorists.tsv.gz, of the stem
types Morpheus gives for every aorist form in the texts. Like the main
Morpheus cache it is committed, so builds need Morpheus only when new forms
appear (then set MORPHEUS, as for build_texts.py).

Usage: python aorists.py <full texts.db>     (refresh the cache)
"""
import gzip
import os
import re
import sqlite3
import subprocess
import sys

import greek

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "morpheus_aorists.tsv.gz")
NL = re.compile(r"<NL>(.*?)</NL>")


def irregular(stemtypes):
    """Second, root and other athematic aorists (εἶπον, ἦλθον, ἔβην, ἔγνων),
    not first (sigmatic) aorists or aorist passives. Morpheus may offer both
    readings for one form; the majority decides."""
    strong = weak = 0
    for s in stemtypes:
        kinds = s.split(",")
        if any("pass" in k for k in kinds):
            continue
        if any(k.startswith("aor2") or k.endswith("_aor") or k.startswith("ath_") for k in kinds):
            strong += 1
        elif "aor1" in kinds:
            weak += 1
    return strong > weak


def load():
    """-> {beta form: [(lemma, stemtype), …]} (aorist analyses only)"""
    out = {}
    if os.path.exists(CACHE):
        with gzip.open(CACHE, "rt", encoding="utf-8") as f:
            for line in f:
                beta, lemma, stem = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                out.setdefault(beta, [])
                if lemma:
                    out[beta].append((lemma, stem))
    return out


def run(forms, morpheus_dir):
    env = dict(os.environ, MORPHLIB=os.path.join(morpheus_dir, "stemlib"))
    text = subprocess.run([os.path.join(morpheus_dir, "bin", "cruncher"), "-S"],
                          input="\n".join(forms) + "\n", capture_output=True, text=True, env=env).stdout
    result, form = {}, None
    for line in text.splitlines():
        if line.startswith(":") or not line.strip():
            continue
        if line.startswith("<NL>"):
            for body in NL.findall(line):
                m = re.match(r"(\w) +(\S+) *([^\t]*)\t([^\t]*)\t([^\t]*)\t?(.*)", body)
                if m and form and " aor " in f" {m.group(3)} ":
                    lemma = greek.from_beta(m.group(2).split(",")[-1])
                    result.setdefault(form, []).append((lemma, m.group(6).strip()))
        else:
            form = line.strip()
            result.setdefault(form, [])
    return result


def aorist_forms(db):
    """Beta Code of every form the texts analyse as an aorist verb."""
    forms = set()
    for form, postag in db.execute("SELECT form, postag FROM token WHERE postag LIKE 'v__a%'"):
        forms.add(form)
    for (form,) in db.execute("SELECT DISTINCT form FROM analysis WHERE rank = 0 AND parse LIKE '%aorist%'"):
        forms.add(form)
    return {greek.to_beta(f) for f in forms}


def main(texts_db):
    cache = load()
    need = sorted(aorist_forms(sqlite3.connect(texts_db)) - set(cache))
    print(f"{len(need)} aorist forms not in the cache", file=sys.stderr)
    if need:
        morpheus_dir = os.environ.get("MORPHEUS")
        if not morpheus_dir:
            sys.exit("set MORPHEUS to a built Morpheus checkout")
        for i in range(0, len(need), 5000):
            found = run(need[i:i + 5000], morpheus_dir)
            for beta in need[i:i + 5000]:
                cache[beta] = found.get(beta, [])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with gzip.open(CACHE, "wt", encoding="utf-8", compresslevel=9) as f:
        for beta in sorted(cache):
            for lemma, stem in cache[beta] or [("", "")]:
                f.write(f"{beta}\t{lemma}\t{stem}\n")


if __name__ == "__main__":
    main(sys.argv[1])
