"""Run the Coptic SCRIPTORIUM NLP pipeline (github.com/CopticScriptorium/coptic-nlp,
Apache 2.0) over Marcion texts and cache what it finds: for every bound group,
its morphemes with lemma and part of speech. The cache is committed
(data/coptic_nlp/*.json.gz), so building the app's databases never needs the
pipeline itself, which wants torch, flair and some old library versions.

Usage:
  python coptic_nlp_cache.py <coptic-nlp checkout> <python with its deps> <dump.msql.bz2> [book ids…]

Setting up the pipeline (Python 3.11; what worked in Nov 2026):
  pip install torch==2.4.1 flair==0.14.0 transformers==4.44.2 pandas==2.2.1 "numpy<2" \\
      scikit-learn==1.4.2 xgboost==0.90 joblib==1.3.2 depedit xmltodict requests gensim
  pip install --no-deps xrenner diaparser
  apt install foma && cp $(which flookup) <coptic-nlp>/bin/foma/
  # the flair model was pickled on Windows:
  echo 'import pathlib; pathlib.WindowsPath = pathlib.PosixPath' > <site-packages>/sitecustomize.py
Only tokenising, normalising, tagging and lemmatising are used (-tln); the
dependency parser needs a model from huggingface.co.

Most of Marcion's texts mark a word broken at a line end with a hyphen, which
nlp_input() rejoins. Some (NHC XI 2b–XIII, the Berlin Apocryphon of John)
do not; for those the line ends are left as spaces and the pipeline's "smart"
re-grouping (-d 3) puts the pieces of each bound group back together.
"""
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

import marcion

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = re.compile(r"fragments", re.I)
NORM = re.compile(r'<norm pos="([^"]*)" lemma="([^"]*)" orig="([^"]*)" norm="([^"]*)"')


def cache_path(collection_name):
    slug = re.sub(r"[^a-z0-9]+", "-", collection_name.lower()).strip("-")
    return os.path.join(HERE, "data", "coptic_nlp", f"{slug}.json.gz")


def load(collection_name):
    path = cache_path(collection_name)
    if not os.path.exists(path):
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def parse_tt(text):
    """-> [[orig_group, [[orig, norm, lemma, pos], …]], …]"""
    groups = []
    for line in text.splitlines():
        if line.startswith("<norm_group "):
            orig = re.search(r'orig_group="([^"]*)"', line).group(1)
            groups.append([orig, []])
        elif line.startswith("<norm ") and groups:
            m = NORM.match(line)
            if m:
                pos, lemma, orig, norm = m.groups()
                groups[-1][1].append([orig, norm, lemma, pos])
    return groups


def needs_regrouping(lines):
    shown = [ln for ln in lines if ln["text"]]
    return sum(ln["text"].endswith("-") for ln in shown) < 0.05 * max(1, len(shown))


def prepare(lines):
    """-> (NLP input text, letter positions, re-grouping level)"""
    detok = 3 if needs_regrouping(lines) else 0
    text, where = marcion.nlp_input(lines, lacuna=" · " if detok else " ")
    return text, where, detok


def input_sha(text, detok):
    return hashlib.sha1(f"{detok}|{text}".encode()).hexdigest()


def run(nlp_dir, python, texts, detok):
    """texts: {book: text} -> {book: groups}"""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(f"{tmp}/in")
        os.makedirs(f"{tmp}/out")
        for book, text in texts.items():
            open(f"{tmp}/in/b{book}.txt", "w", encoding="utf-8").write(text + "\n")
        done = subprocess.run([python, "-W", "ignore", "coptic_nlp.py", "-tln", "-d", str(detok), "-q",
                               "-o", "sgml", "--dirout", f"{tmp}/out", f"{tmp}/in/*.txt"],
                              cwd=nlp_dir, check=True, capture_output=True, text=True)
        out = {}
        for book in texts:
            # with a single input file the pipeline writes to stdout
            tt = (done.stdout if len(texts) == 1
                  else open(f"{tmp}/out/b{book}.tt", encoding="utf-8").read())
            out[book] = parse_tt(tt)
        return out


def main(nlp_dir, python, dump, *only):
    coll, books, rows = marcion.read_dump(dump)
    fmt = coll.get("format", "2")
    cache = load(coll["name"])
    todo = {0: {}, 3: {}}
    for book, (name, _) in books.items():
        if SKIP.search(name) or (only and str(book) not in only):
            continue
        lines = marcion.book_lines(rows, book, fmt)
        text, _, detok = prepare(lines)
        sha = input_sha(text, detok)
        if cache.get(str(book), {}).get("input_sha") != sha:
            todo[detok][book] = (text, sha)
    print(f"{coll['name']}: {sum(map(len, todo.values()))} books to analyse", file=sys.stderr)
    for detok, books_todo in todo.items():
        if books_todo:
            groups = run(nlp_dir, python, {b: t for b, (t, _) in books_todo.items()}, detok)
            for book, (_, sha) in books_todo.items():
                cache[str(book)] = dict(input_sha=sha, detok=detok, groups=groups[book])
    path = cache_path(coll["name"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
    print(path, os.path.getsize(path), file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])
