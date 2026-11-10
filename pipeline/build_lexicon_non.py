"""The Old Norse dictionaries, as a downloadable dictionary module.

  python build_lexicon_non.py <sources> <texts.db> <lexicon_non.db>

Old Norse is the one language whose dictionaries do not ship with the app:
they are a module of their own (dict-non.db.z, see make_modules.py and
make_catalog.py), which the app downloads with the first Old Norse text and
keeps as Library/lexicon-non.db beside the bundled lexicon.db. Same tables as
lexicon.db (build_lexicon.SCHEMA, RESOLVE_SCHEMA), plus `meta` with the build
id (stamp_build.py), so the app opens it the same way.

  - zoega: Geir T. Zoëga, A Concise Dictionary of Old Icelandic (1910); the
    short definitions are its glosses.
  - cv: Richard Cleasby and Gudbrand Vigfusson, An Icelandic-English
    Dictionary (1874).
Both public domain, from stscoundrel's digitizations (MIT).

Lemma keys from the texts (non:…, see oldnorse.py) are resolved to entries
here, at build time: the headword as keyed, else without accents.
"""
import json
import os
import re
import sqlite3
import sys
import unicodedata
import zlib
from collections import Counter

import build_lexicon
import oldnorse as on

DICTS = [
    ("zoega", "Geir T. Zoëga, A Concise Dictionary of Old Icelandic (1910)",
     "Public domain; digitized by stscoundrel/old-icelandic-zoega (MIT)"),
    ("cv", "Cleasby & Vigfusson, An Icelandic-English Dictionary (1874)",
     "Public domain; digitized by stscoundrel/cleasby-vigfusson-dictionary (MIT)"),
]


def headword(w):
    return unicodedata.normalize("NFC", w.strip()).lower()


def bare(k):
    return on.strip_accents(k)


def html(hw, definitions):
    """An entry in the app's entry styles (.hw .sense)."""
    parts = [f'<div class="hw">{hw}</div>']
    for d in definitions:
        d = d.strip()
        if not d or re.fullmatch(r"<strong>[IVX\d]+[.)]</strong>", d):
            continue
        parts.append(f'<div class="sense">{d}</div>')
    return "".join(parts)


def zoega_gloss(definitions):
    """'stallion; horse': the italic glosses of the numbered senses (or of the
    first sense, if the entry is not numbered)."""
    senses = [d for d in definitions if re.match(r"\s*\d+\)", d)] or definitions[:3]
    out = []
    for d in senses:
        m = re.search(r"<i>(.*?)</i>", d)
        if m:
            g = re.sub(r"<[^>]+>", "", m.group(1)).strip(" ,;.")
            if g and g not in out:
                out.append(g)
        if len(out) >= 3:
            break
    return "; ".join(out)[:120] or None


def add(db, path, d, sizes, gloss=False):
    entries = json.load(open(path, encoding="utf-8"))
    homographs = Counter()
    for e in entries:
        hw = headword(e["word"])
        if not hw:
            continue
        key = on.key(hw)
        homographs[key] += 1
        comp = zlib.compress(html(hw, e["definitions"]).encode("utf-8"), 9)[2:-4]
        db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                   (d, hw, key, bare(key), homographs[key], comp))
        sizes[f"{d}_entries"] += 1
        if gloss:
            g = zoega_gloss(e["definitions"])
            if g:
                db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (key, bare(key), hw, g))
                sizes["shortdefs"] += 1


# spellings and short forms the dictionaries enter under another headword
ALIASES = {"fyr": ["fyrir"], "þvíat": ["því", "þvíat"], "es": ["er"], "hon": ["hón"], "gera": ["gøra", "göra", "gjöra"],
           "eða": ["eðr", "eða"], "fyrstr": ["fyrstr", "fyrsti"], "í": ["í", "i"], "mjök": ["mjök", "mjög"]}


def resolve(db, d, key):
    """(entry ids, how): the headword as keyed, else an alias, else the same
    letters without accents."""
    if d == "short":
        q = "SELECT rowid FROM shortdef WHERE {} = ?"
    else:
        q = f"SELECT id FROM entry WHERE dict='{d}' AND {{}} = ? ORDER BY homograph"
    hits = [r[0] for r in db.execute(q.format("key"), (key,))]
    if hits:
        return hits, "exact"
    for alt in ALIASES.get(key[len(on.PREFIX):], []):
        hits = [r[0] for r in db.execute(q.format("key"), (on.key(alt),))]
        if hits:
            return hits, "alias"
    hits = [r[0] for r in db.execute(q.format("bare"), (bare(key),))]
    return hits[:3], ("accentless" if hits else None)


def main(sources, texts_db, out):
    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript(build_lexicon.SCHEMA + build_lexicon.RESOLVE_SCHEMA)
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", DICTS)
    sizes = Counter()
    add(db, os.path.join(sources, "zoega", "json", "zoega.json"), "zoega", sizes, gloss=True)
    add(db, os.path.join(sources, "cleasby", "json", "cleasby-vigfusson.json"), "cv", sizes)
    db.commit()

    tdb = sqlite3.connect(texts_db)
    counts = Counter(r[0] for r in tdb.execute(
        "SELECT t.lemma_key FROM token t JOIN segment s ON s.id = t.segment_id JOIN work w ON w.id = s.work_id "
        "WHERE w.language = 'non'") if r[0])
    keys = set(counts) | {r[0] for r in tdb.execute("SELECT DISTINCT lemma_key FROM analysis") if on.is_old_norse(r[0])}
    found = {}
    for key in keys:
        for d in ("zoega", "cv", "short"):
            hits, how = resolve(db, d, key)
            for target in hits:
                db.execute("INSERT INTO resolve VALUES (?,?,?,?)", (key, d, target, how))
            found[(key, d)] = how
    db.commit()
    total = sum(counts.values()) or 1
    report = {"sizes": dict(sizes)}
    for d in ("zoega", "cv", "short"):
        by = Counter()
        miss = Counter()
        for key, n in counts.items():
            how = found.get((key, d))
            by[how or "missing"] += n
            if not how:
                miss[key] += n
        report[d] = {"coverage_pct": {k: round(100 * v / total, 1) for k, v in by.items()},
                     "top_misses": miss.most_common(15)}
    db.execute("VACUUM")
    db.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
