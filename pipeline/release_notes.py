"""Write the notes and credits for a texts release (publish_release.sh).

  python release_notes.py <catalog.json> <notes.md> <CREDITS.md>

The credits are taken from the app's own credit lines (LibraryView.swift), so
the release and the app never disagree."""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY_VIEW = os.path.join(HERE, "..", "app", "AncientLanguages", "Library", "LibraryView.swift")
LANGUAGES = [("greek", "Greek"), ("latin", "Latin"), ("hebrew", "Hebrew"), ("sanskrit", "Sanskrit"),
             ("coptic", "Coptic"), ("oldEnglish", "Old English")]
NAMES = {"grc": "Greek", "lat": "Latin", "hbo": "Hebrew", "san": "Sanskrit", "cop": "Coptic", "ang": "Old English"}

LICENCES = """Each text keeps the licence of its sources, given in CREDITS.md. In summary:

- Perseus Digital Library texts, translations and treebanks: CC BY-SA.
- SBL Greek New Testament and MACULA data, Open Scriptures Hebrew Bible, STEPBible, Coptic SCRIPTORIUM, Digital Corpus of Sanskrit: CC BY 4.0.
- PROIEL treebank parses (Vulgate, Caesar): CC BY-NC-SA 4.0 (non-commercial; this project is free and non-commercial).
- Nag Hammadi and Berlin Codex texts from Marcion by Milan Konvička: GPL.
- Sahidic Bible 2: CC BY-SA. Old English (ASPR, Hidley): CC BY-SA.
- Translations from Project Gutenberg, Wikisource and sacred-texts.com, the Berean Standard Bible and the Brenton Septuagint: public domain or CC0."""


def credits():
    src = open(LIBRARY_VIEW, encoding="utf-8").read()
    out = []
    for key, name in LANGUAGES:
        m = re.search(r'static let ' + key + r'Credits = "((?:[^"\\]|\\.)*)"', src)
        if m:
            out.append(f"## {name}\n\n{m.group(1)}\n")
    return "\n".join(out)


def main(catalog_path, notes_path, credits_path):
    c = json.load(open(catalog_path, encoding="utf-8"))
    works = c["works"]
    langs = Counter(NAMES.get(w["language"], w["language"]) for w in works)
    size = sum(w["bytes"] or 0 for w in works)
    with open(credits_path, "w", encoding="utf-8") as f:
        f.write(f"# Credits and licences (texts build {c['build']})\n\n{credits()}")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(f"""Texts for the Ancient Languages app, build `{c['build']}`.

These files are data, not code: one compressed SQLite module per text ({len(works)} texts, \
{size / 1e6:.0f} MB in all: {", ".join(f"{n} {l}" for l, n in langs.most_common())}). \
The app downloads them from here when a reader adds a text; app versions built with this \
build's `catalog.json` use only this release, so it should be kept.

{LICENCES}
""")
    print(f"{notes_path}, {credits_path}: {len(works)} works, {size / 1e6:.0f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
