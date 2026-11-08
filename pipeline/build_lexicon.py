"""Spike: build lexicon.db from LSJ (Logeion), Middle Liddell (Logeion) and
Logeion short definitions, then report how many lemmas in texts.db resolve.

Usage: python build_lexicon.py <LSJLogeion dir> <MiddleLiddell dir> <shortdefs file> <texts.db> <out.db>
"""
import glob
import html
import json
import os
import lzma
import re
import sqlite3
import sys
import zlib
from collections import Counter

from lxml import etree

import coptic
import greek
import latin
import oldenglish
import hebrew
import sanskrit

SCHEMA = """
CREATE TABLE dictionary (id TEXT PRIMARY KEY, title TEXT, credit TEXT);
CREATE TABLE entry (
  id INTEGER PRIMARY KEY, dict TEXT, headword TEXT, key TEXT, bare TEXT,
  homograph INT, html BLOB, pos TEXT);
CREATE INDEX entry_key ON entry(key, dict);
CREATE INDEX entry_bare ON entry(bare, dict);
CREATE TABLE shortdef (key TEXT, bare TEXT, lemma TEXT, def TEXT, pos TEXT);
CREATE INDEX shortdef_key ON shortdef(key);
CREATE INDEX shortdef_bare ON shortdef(bare);
-- Coptic entries are found through all their attested forms, not just the headword.
CREATE TABLE form_key (key TEXT, dict TEXT, entry_id INT, rank INT);
CREATE INDEX form_key_key ON form_key(key, dict);
"""

# Which entries a text lemma opens, decided at build time so the app needs no
# Greek normalisation logic for taps.  how = exact | alias | accentless.
RESOLVE_SCHEMA = """
CREATE TABLE resolve (lemma_key TEXT, dict TEXT, target INT, how TEXT);
CREATE INDEX resolve_key ON resolve(lemma_key);
"""

# Lemmatisation conventions differ between the treebank and the dictionaries.
ALIASES = {
    "πρῶτοσ": ["πρότεροσ"], "ταὐτόσ": ["αὐτόσ"], "σαυτοῦ": ["σεαυτοῦ"],
    "κεῖνοσ": ["ἐκεῖνοσ"], "ἠέλιοσ": ["ἥλιοσ"], "πάτρη": ["πάτρα"],
    "νυνδί": ["νυνί"], "οὑτωσί": ["οὕτωσ"],
}
SUFFIX_RULES = [("ομαι", "ω"), ("ήσκω", "ῄσκω"), ("τέοσ", "τέον"), ("η", "α")]


def candidates(key, d=None):
    yield key, "exact"
    for alt in ALIASES.get(key, []):
        yield alt, "alias"
    if d == "aut":
        yield from homeric_candidates(key)
    for old, new in SUFFIX_RULES:
        if key.endswith(old):
            yield key[: -len(old)] + new, "alias"


# Autenrieth lists Homer's (Ionic) forms, where the treebank and Morpheus
# lemmatise to Attic ones: βία → βίη, ξένος → ξεῖνος, Ἀχιλλεύς → Ἀχιλεύς.
HOMERIC_ALIASES = {
    "ξένοσ": ["ξεῖνοσ"], "αὖθισ": ["αὖτισ"], "ἱερόσ": ["ἱρόσ"], "εἶδον": ["εἴδω"],
    "μόνοσ": ["μοῦνοσ"], "κόρη": ["κούρη"], "κόροσ": ["κοῦροσ"], "ὄνομα": ["οὔνομα"],
    "νόσοσ": ["νοῦσοσ"], "ὅροσ": ["οὖροσ"], "πολύσ": ["πολλόσ"],
    "τισ": ["τίσ"], "πέπνυμαι": ["πνέω"], "ἀχαιόσ": ["ἀχαιοί"], "πρόσθεν": ["πρόσθε"],
    "οὕτωσ": ["οὕτω"], "πυκνόσ": ["πυκινόσ"], "ποσειδεών": ["ποσειδάων"], "τλάω": ["τέτλαθι"],
    "σώζω": ["σαόω", "σάω"], "κρατήρ": ["κρητήρ"], "λίαν": ["λίην"], "ὄπισθεν": ["ὄπισθε"],
    "ὦκα": ["ὦκ"], "οὐτάω": ["οὐτάζω"], "δάιοσ": ["δήιοσ", "δάϊοσ"],
    "ναόσ": ["νηόσ"],
}


def homeric_candidates(key):
    for alt in HOMERIC_ALIASES.get(key, []):
        yield alt, "alias"
    if key.endswith("α"):                       # -α → -η (βία, θύρα, κλισία, Τροία)
        yield key[:-1] + "η", "alias"
    if key.endswith("ά"):
        yield key[:-1] + "ή", "alias"
    for double, single in (("λλ", "λ"), ("σσ", "σ")):   # Ἀχιλλεύς, Ὀδυσσεύς
        if double in key:
            yield key.replace(double, single, 1), "alias"


# Compounds the lexica list under their second element: ⲣ̄-ⲛⲏⲥⲧⲉⲩⲉ (do fasting),
# ϯ-ⲉⲗⲉⲏⲙⲟⲥⲩⲛⲏ (give alms); and pronominal forms with a suffix: ⲧⲏⲣ-ϥ.
COPTIC_PREFIXES = ["ⲣ", "ϯ", "ϫⲓ", "ϭⲓ", "ⲙⲛⲧ", "ⲣⲉϥ", "ⲁⲧ", "ⲣⲙⲛ", "ϣⲡ", "ⲙⲉϩ"]
COPTIC_SUFFIXES = ["ϥ", "ⲥ", "ⲟⲩ", "ⲕ", "ⲧ", "ⲛ", "ⲧⲛ"]


def coptic_candidates(key):
    yield key, "exact"
    for v in coptic.spelling_variants(key):
        yield v, "alias"
    for p in COPTIC_PREFIXES:
        if key.startswith(p) and len(key) > len(p) + 1:
            yield key[len(p):], "alias"
    for x in COPTIC_SUFFIXES:
        if key.endswith(x) and len(key) > len(x) + 1:
            yield key[: -len(x)], "alias"


def resolve_coptic(db, d, key):
    for cand, how in coptic_candidates(key):
        if d == "short":
            hits = [r[0] for r in db.execute("SELECT rowid FROM shortdef WHERE key = ?", (cand,))]
            if hits:
                return hits[:6], how     # homographs: the app picks by part of speech
            continue
        hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict=? AND key=? ORDER BY homograph", (d, cand))]
        if hits:
            return hits, how
        hits = [r[0] for r in db.execute("SELECT entry_id FROM form_key WHERE dict=? AND key=? ORDER BY rank",
                                         (d, cand))]
        if hits:
            return list(dict.fromkeys(hits))[:3], "form" if how == "exact" else how
    return [], None


def resolve(db, d, key):
    if sanskrit.is_sanskrit_key(key):
        return resolve_sanskrit(db, d, key)
    if hebrew.is_hebrew_key(key):
        return resolve_hebrew(db, d, key)
    if oldenglish.is_old_english(key):
        return resolve_old_english(db, d, key)
    if coptic.is_coptic(key):
        return resolve_coptic(db, d, key)
    if latin.is_latin(key):
        q = "SELECT rowid FROM shortdef WHERE key = ?" if d == "short" else \
            f"SELECT id FROM entry WHERE dict='{d}' AND key = ? ORDER BY homograph"
        for cand in latin_candidates(key):
            hits = [r[0] for r in db.execute(q, (cand,))]
            if hits:
                return hits, "exact" if cand == key else "alias"
        return [], None
    if d == "short":
        q = "SELECT rowid FROM shortdef WHERE {} = ?"
    else:
        q = f"SELECT id FROM entry WHERE dict='{d}' AND {{}} = ? ORDER BY homograph"
    for cand, how in candidates(key, d):
        hits = [r[0] for r in db.execute(q.format("key"), (cand,))]
        if hits:
            return hits, how
    if d == "abs" and NT_STRONG.get(key) in ABBOTT_STRONG:     # same word, spelled differently
        return ABBOTT_STRONG[NT_STRONG[key]], "alias"
    hits = [r[0] for r in db.execute(q.format("bare"), (greek.bare(key),))]
    return hits[:3], "accentless"

PARSER = etree.XMLParser(recover=True)
ENTRY_RE = {
    "lsj": re.compile(r"<div2\b.*?</div2>", re.S),
    "ml": re.compile(r"<div1\b.*?</div1>", re.S),
}


def to_html(el):
    """Small TEI -> HTML mapping for dictionary articles."""
    out = []

    def rec(e):
        name = e.tag if isinstance(e.tag, str) else ""
        open_, close = "", ""
        if name == "head":
            open_, close = '<b class="hw">', "</b>"
        elif name == "sense":
            n = e.get("n") or ""
            lvl = e.get("level") or "1"
            label = f'<b class="sn">{html.escape(n)}.</b> ' if n and n != "0" else ""
            open_, close = f'<div class="sense l{lvl}">{label}', "</div>"
        elif name in ("i", "trans", "tr"):
            open_, close = "<i>", "</i>"
        elif name == "bibl":
            open_, close = f'<span class="bibl" data-ref="{html.escape(e.get("n") or "")}">', "</span>"
        elif name in ("quote", "foreign", "orth") and (e.get("lang") or "").startswith("grc"):
            open_, close = '<span class="gk">', "</span>"
        elif name in ("author", "usg"):
            open_, close = '<span class="au">', "</span>"
        elif name == "title":
            open_, close = '<span class="ti">', "</span>"
        elif name == "etym":
            open_, close = '<span class="etym">', "</span>"
        out.append(open_)
        if e.text:
            out.append(html.escape(e.text))
        for c in e:
            rec(c)
        out.append(close)
        if e.tail and e is not el:
            out.append(html.escape(e.tail))

    rec(el)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def iter_entries(paths, kind):
    for p in sorted(paths):
        text = open(p, encoding="utf-8").read()
        for m in ENTRY_RE[kind].finditer(text):
            el = etree.fromstring(m.group(0), PARSER)
            if el is None:
                continue
            head = el.find("head")
            hw = "".join(head.itertext()).strip() if head is not None else el.get("key")
            yield hw, to_html(el)


BETA_WORD = re.compile(r"[A-Za-z*()/\\=+|_^'0-9]+")


def beta_phrase(text):
    """Beta Code running text -> Unicode, word by word (spaces and punctuation
    kept). Autenrieth writes digamma as v."""
    def word(m):
        return "ϝ".join(greek.from_beta(part, quantity=True) for part in m.group().split("v"))
    return BETA_WORD.sub(word, text)


def autenrieth_html(el):
    """Autenrieth's TEI (Beta Code Greek, TEI P3) -> the same small HTML."""
    out = []

    def gk(text):
        return html.escape(beta_phrase(text or ""))

    def rec(e, greek_text=False):
        name = e.tag if isinstance(e.tag, str) else ""
        is_greek = greek_text or (e.get("lang") == "greek")
        open_, close = "", ""
        if name == "orth":
            open_, close = '<b class="hw">', "</b>"
        elif name == "foreign" and is_greek:
            open_, close = '<span class="gk">', "</span>"
        elif name == "gloss":
            open_, close = "<i>", "</i>"
        elif name == "bibl":
            open_, close = f'<span class="bibl" data-ref="{html.escape(e.get("n") or "")}">', "</span>"
        elif name in ("figure", "pb"):
            if e.tail:
                out.append(html.escape(e.tail))
            return
        out.append(open_)
        if e.text:
            out.append(gk(e.text) if is_greek else html.escape(e.text))
        for c in e:
            rec(c, is_greek)
        out.append(close)
        if e.tail and e is not el:
            out.append(html.escape(e.tail))   # a tail belongs to the parent: English

    rec(el)
    body = re.sub(r"\s+", " ", "".join(out)).strip()
    return body.replace("(See cut.)", "").strip()


def iter_autenrieth(path):
    """Yield (headword, lookup key, html) for each entry of Autenrieth's
    Homeric Dictionary (Perseus TEI, Perseus:text:1999.04.0073)."""
    root = etree.parse(path, PARSER).getroot()
    for el in root.iter("entryFree"):
        key = greek.from_beta(el.get("key") or "")
        orth = el.find("orth")
        hw = beta_phrase((orth.text if orth is not None else el.get("key")) or "").replace("-", "")
        yield hw, greek.lex_key(key), autenrieth_html(el)


def abbott_html(el):
    """Abbott-Smith's TEI (Crosswire TEI-OSIS) -> the same small HTML."""
    out = []

    def rec(e, depth=0):
        if not isinstance(e.tag, str):            # comments
            if e.tail:
                out.append(html.escape(e.tail))
            return
        name = etree.QName(e).localname
        lang = e.get("{http://www.w3.org/XML/1998/namespace}lang") or ""
        open_, close = "", ""
        if name == "orth":
            open_, close = '<b class="hw">', "</b>"
        elif name == "foreign" and lang == "grc":
            open_, close = '<span class="gk">', "</span>"
        elif name == "foreign" and lang == "heb":
            open_, close = '<span class="he" dir="rtl">', "</span>"
        elif name in ("gloss",):
            open_, close = "<i>", "</i>"
        elif name in ("emph", "hi"):
            open_, close = "<em>", "</em>"
        elif name == "ref":
            open_, close = f'<span class="bibl" data-ref="{html.escape(e.get("osisRef") or "")}">', "</span>"
        elif name == "etym":
            open_, close = '<span class="etym">', "</span>"
        elif name in ("sense", "re"):
            n = e.get("n") or ""
            label = f'<b class="sn">{html.escape(n)}</b> ' if n else ""
            open_, close = f'<div class="sense l{min(depth + 1, 4)}">{label}', "</div>"
            depth += 1
        elif name == "note" and e.get("type") == "occurrencesNT":
            out.append(f'<span class="occ">{html.escape((e.text or "").strip())}× in the NT.</span> ')
            if e.tail:
                out.append(html.escape(e.tail))
            return
        elif name == "pb":
            if e.tail:
                out.append(html.escape(e.tail))
            return
        out.append(open_)
        if e.text:
            out.append(html.escape(e.text))
        for c in e:
            rec(c, depth)
        out.append(close)
        if e.tail and e is not el:
            out.append(html.escape(e.tail))

    rec(el)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def iter_abbott(path):
    """Yield (headword, lookup key, Strong's number or None, short gloss, html)
    for each entry of Abbott-Smith's Manual Greek Lexicon of the NT."""
    root = etree.parse(path, PARSER).getroot()
    for el in root.iter("{*}entry"):
        n = el.get("n") or ""
        hw, _, strong = n.partition("|")
        hw = hw.strip()
        if not hw:
            continue
        glosses = []
        for g in el.iter("{*}gloss"):
            t = re.sub(r"\s+", " ", "".join(g.itertext())).strip(" ,;:.")
            if t and t not in glosses:
                glosses.append(t)
        yield hw, greek.lex_key(hw), strong.lstrip("G") or None, ", ".join(glosses[:3]), abbott_html(el)


def latin_html(el):
    """Lewis & Short / Lewis's Elementary Latin Dictionary (Perseus TEI) ->
    the same small HTML as the Greek lexica."""
    out = []
    first_orth = [True]

    def rec(e):
        if not isinstance(e.tag, str):
            if e.tail:
                out.append(html.escape(e.tail))
            return
        name = etree.QName(e).localname
        lang = e.get("lang") or ""
        open_, close = "", ""
        if name == "orth":
            if first_orth[0]:
                open_, close = '<b class="hw">', "</b>"
                first_orth[0] = False
            else:
                open_, close = "<b>", "</b>"
        elif name == "foreign" and lang.startswith("gr"):
            open_, close = '<span class="gk">', "</span>"
        elif name in ("tr", "hi", "emph") or (name == "foreign" and lang == "la"):
            open_, close = "<i>", "</i>"
        elif name == "bibl":
            open_, close = f'<span class="bibl" data-ref="{html.escape(e.get("n") or "")}">', "</span>"
        elif name in ("author", "usg"):
            open_, close = '<span class="au">', "</span>"
        elif name == "etym":
            open_, close = '<span class="etym">', "</span>"
        elif name == "sense":
            n = e.get("n") or ""
            lvl = e.get("level") or "1"
            label = f'<b class="sn">{html.escape(n)}.</b> ' if n and n != "0" else ""
            open_, close = f'<div class="sense l{lvl}">{label}', "</div>"
        elif name in ("pb", "cb"):
            if e.tail:
                out.append(html.escape(e.tail))
            return
        out.append(open_)
        if e.text:
            out.append(html.escape(e.text))
        for c in e:
            rec(c)
        out.append(close)
        if e.tail and e is not el:
            out.append(html.escape(e.tail))

    rec(el)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _unescape_entities(text):
    """Named HTML entities (&amacr;) that XML parsers don't know."""
    keep = {"lt", "gt", "amp", "quot", "apos"}
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);",
                  lambda m: m.group(0) if m.group(1) in keep else html.unescape(m.group(0)), text)


def iter_latin(path, tag):
    """Yield (headword, key, short gloss, html) for each entry of a Perseus
    Latin dictionary (`tag`: entryFree for Lewis & Short, entry for Lewis's
    Elementary Latin Dictionary)."""
    import latin
    text = _unescape_entities(open(path, encoding="utf-8").read())
    root = etree.fromstring(text.encode("utf-8"), etree.XMLParser(recover=True, huge_tree=True))
    for el in root.iter(tag):
        k = el.get("key") or ""
        orth = el.find(".//orth")
        hw = re.sub(r"\s+", " ", "".join(orth.itertext())).strip(" .,") if orth is not None else k
        trs = []
        for t in el.iter("tr"):
            g = re.sub(r"\s+", " ", "".join(t.itertext())).strip(" ,;:.")
            if g and g not in trs:
                trs.append(g)
        yield hw or k, latin.key(k), ", ".join(trs[:3]), latin_html(el)


def add_latin(db, ls_path, lewis_path, latin_shortdefs, sizes):
    import latin
    if not ls_path:
        return
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", [
        ("ls", "Lewis & Short, A Latin Dictionary (1879)",
         "Perseus Digital Library, Tufts University (http://www.perseus.tufts.edu/). CC BY-SA"),
        ("lewis", "Charlton T. Lewis, An Elementary Latin Dictionary (1890)",
         "Perseus Digital Library, Tufts University (http://www.perseus.tufts.edu/). CC BY-SA"),
    ])
    glosses = {}
    for d, path, tag in (("ls", ls_path, "entryFree"), ("lewis", lewis_path, "entry")):
        if not path:
            continue
        seen = Counter()
        for hw, key, gloss, h in iter_latin(path, tag):
            seen[key] += 1
            comp = zlib.compress(h.encode("utf-8"), 9)[2:-4]
            db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                       (d, hw, key, key, seen[key], comp))
            if gloss and d == "lewis":
                glosses.setdefault(key, (hw, gloss))
            sizes[f"{d}_entries"] += 1
    have = set()
    if latin_shortdefs:
        for line in open(latin_shortdefs, encoding="utf-8"):
            hw, _, d = line.rstrip("\n").partition("\t")
            d = re.sub(r"\s+", " ", d).strip()
            if hw and d:
                k = latin.key(hw)
                have.add(k)
                db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (k, k, hw, d))
                sizes["shortdefs_latin"] += 1
    for k, (hw, g) in glosses.items():           # Lewis's glosses where Logeion has none
        if k not in have:
            db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (k, k, hw, g))
            sizes["shortdefs_latin_lewis"] += 1


def add_coptic(db, ccl_path, crum_path, sizes):
    """Comprehensive Coptic Lexicon (default) and Crum (via Marcion)."""
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", [
        ("ccl", "Comprehensive Coptic Lexicon (v1.2, 2020)",
         "BBAW Lexicon of Coptic Egyptian and DDGLC Lexicon of Greek Loanwords in Coptic; "
         "KELLIA / Coptic SCRIPTORIUM. CC BY-SA 4.0"),
        ("crum", "W. E. Crum, A Coptic Dictionary (1939)",
         "Digitised in Marcion by Milan Konvicka (marcion.sourceforge.net), GPL v2"),
    ])
    sources = []
    if ccl_path:
        sources.append(("ccl", coptic.read_ccl(ccl_path)))
    if crum_path:
        sources.append(("crum", ((h, k, body, g, None) for h, k, body, g, _ in coptic.read_crum(crum_path))))
    for d, entries in sources:
        seen = Counter()
        for headword, keys, body, gloss, pos in entries:
            pos = pos if isinstance(pos, str) else None
            if not keys:
                continue
            seen[keys[0]] += 1
            comp = zlib.compress(body.encode("utf-8"), 9)[2:-4]
            eid = db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html,pos) VALUES (?,?,?,?,?,?,?)",
                             (d, headword, keys[0], keys[0], seen[keys[0]], comp, pos)).lastrowid
            for rank, k in enumerate(keys):
                db.execute("INSERT INTO form_key VALUES (?,?,?,?)", (k, d, eid, rank))
            if d == "ccl" and gloss:
                db.execute("INSERT INTO shortdef VALUES (?,?,?,?,?)", (keys[0], keys[0], headword, gloss, pos))
            sizes[f"{d}_entries"] += 1


HEB_INDEX = {}          # Hebrew lemma key -> (BDB entry id, Strong's id)


def heb_html(el):
    """BDB / Strong's XML -> simple HTML (Hebrew words marked so they render right to left)."""
    import html as _h

    def rec(e):
        name = e.tag.split("}")[-1] if isinstance(e.tag, str) else ""
        inner = _h.escape(e.text or "", quote=False) + "".join(
            rec(c) + _h.escape(c.tail or "", quote=False) for c in e if name != "status")
        if name == "status":
            return ""
        if name == "w":
            return f'<span dir="rtl" lang="he" class="heb">{inner}</span>'
        if name == "def":
            return f"<b>{inner}</b>"
        if name in ("pos", "em", "foreign"):
            return f"<i>{inner}</i>"
        if name == "sense":
            return f"<p>{(e.get('n') + '. ') if e.get('n') else ''}{inner}</p>"
        if name in ("source", "meaning", "usage"):
            label = {"source": "", "meaning": "", "usage": "<i>KJV:</i> "}[name]
            return f"<p>{label}{inner}</p>"
        return inner
    return " ".join(rec(el).split())


def add_hebrew(db, lexdir, sizes):
    """BDB (default) and Strong's, from the Open Scriptures Hebrew Lexicon
    (CC BY 4.0; the dictionaries' text is public domain). Short definitions
    from its lexical index, which also links the text's lemmas (augmented
    Strong's numbers) to the BDB entries."""
    if not lexdir or not os.path.isdir(lexdir):
        return
    ns = "{http://openscriptures.github.com/morphhb/namespace}"
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", [
        ("bdb", "Brown, Driver & Briggs, A Hebrew and English Lexicon of the Old Testament (1906)",
         "Open Scriptures Hebrew Lexicon (CC BY 4.0); text public domain"),
        ("strong", "Strong's Hebrew Dictionary (1890)", "Open Scriptures Hebrew Lexicon (CC BY 4.0); text public domain"),
    ])
    for e in etree.parse(os.path.join(lexdir, "BrownDriverBriggs.xml")).getroot().iter(ns + "entry"):
        w = e.find(ns + "w")
        comp = zlib.compress(heb_html(e).encode("utf-8"), 9)[2:-4]
        db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                   ("bdb", w.text if w is not None else "", "bdb:" + e.get("id"), e.get("id"), 1, comp))
        sizes["bdb_entries"] += 1
    for e in etree.parse(os.path.join(lexdir, "HebrewStrong.xml")).getroot().iter():
        if e.tag.split("}")[-1] != "entry" or not e.get("id"):
            continue
        w = next((c for c in e if c.tag.split("}")[-1] == "w"), None)
        comp = zlib.compress(heb_html(e).encode("utf-8"), 9)[2:-4]
        db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                   ("strong", w.text if w is not None else "", e.get("id"), e.get("id"), 1, comp))
        sizes["strong_entries"] += 1
    aug = {w.get("aug"): w.text for w in etree.parse(os.path.join(lexdir, "AugIndex.xml")).getroot().iter(ns + "w")}
    li = {}
    for e in etree.parse(os.path.join(lexdir, "LexicalIndex.xml")).getroot().iter(ns + "entry"):
        w, d, x, p = e.find(ns + "w"), e.find(ns + "def"), e.find(ns + "xref"), e.find(ns + "pos")
        li[e.get("id")] = (w.text if w is not None else None, d.text if d is not None else None,
                           x.get("bdb") if x is not None else None, x.get("strong") if x is not None else None,
                           p.text if p is not None else None)
    # STEPBible's brief lexicon (TBESH, CC BY 4.0) has the better one-line glosses
    # ("to create" where the index has "shape"); its first line per number
    brief = {}
    for path in glob.glob(os.path.join(os.path.dirname(lexdir.rstrip("/")), "STEPBible-Data", "Lexicons", "TBESH*.txt")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) > 6 and re.match(r"^H\d{4}[a-z]?$", c[0]) and c[0] not in brief:
                    brief[c[0]] = (c[3], c[6].strip())
    for a, lid in aug.items():
        word, gloss, bdb, strong, pos = li.get(lid, (None,) * 5)
        key = hebrew.PREFIX + a
        m = re.match(r"(\d+)([a-z]?)$", a)
        if m and f"H{int(m.group(1)):04d}{m.group(2)}" in brief:
            word2, g2 = brief[f"H{int(m.group(1)):04d}{m.group(2)}"]
            if g2:
                gloss, word = g2.strip(":; "), word or word2
        HEB_INDEX[key] = (bdb, f"H{strong}" if strong else (f"H{re.match(r'[0-9]+', a).group()}"
                                                            if re.match(r"[0-9]+", a) else None))
        if gloss:
            db.execute("INSERT INTO shortdef VALUES (?,?,?,?,?)", (key, key, word, gloss, pos))
            sizes["shortdefs_hebrew"] += 1
    for letter, (word, gloss) in hebrew.PARTICLES.items():
        db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (hebrew.PREFIX + letter, hebrew.PREFIX + letter,
                                                                    word, gloss))


def resolve_hebrew(db, d, key):
    if d == "short":
        hits = [r[0] for r in db.execute("SELECT rowid FROM shortdef WHERE key=?", (key,))]
        if not hits and re.search(r"[a-z]$", key):          # 1254a -> 1254
            hits = [r[0] for r in db.execute("SELECT rowid FROM shortdef WHERE key=?", (key[:-1],))]
        return hits, "exact" if hits else None
    bdb, strong = HEB_INDEX.get(key) or HEB_INDEX.get(re.sub(r"[a-z]$", "", key)) or (None, None)
    if d == "bdb" and bdb:
        hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict='bdb' AND key=?", ("bdb:" + bdb,))]
        return hits, "exact" if hits else None
    if d == "strong":
        n = strong or (f"H{re.match(r'[0-9]+', key[len(hebrew.PREFIX):]).group()}"
                       if re.match(r"[0-9]+", key[len(hebrew.PREFIX):]) else None)
        if n:
            hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict='strong' AND key=?", (n,))]
            return hits, "exact" if hits else None
    return [], None


SAN_KEYS = set()         # Sanskrit headwords (SLP1) present, per dictionary: {(dict, k1)}
SAN_VERBS = set()        # Sanskrit lemmas the texts use as verbs


def add_sanskrit(db, sources, texts_db, sizes):
    """Macdonell's Practical Sanskrit Dictionary (default; whole) and
    Monier-Williams (the entries the texts' lemmas can reach), from the
    Cologne Digital Sanskrit Dictionaries (CC BY-SA 4.0); short definitions
    from the Digital Corpus of Sanskrit's lemma dictionary (CC BY 4.0)."""
    if not sources:
        return
    md = os.path.join(sources, "csl-orig", "v02", "md", "md.txt")
    mw = os.path.join(sources, "csl-orig", "v02", "mw", "mw.txt")
    dcs = os.path.join(sources, "dcs", "dcs", "data", "conllu", "lookup", "dictionary.csv")
    tdb = sqlite3.connect(texts_db)
    lemmas = set()
    for table in ("token", "morph"):
        lemmas |= {r[0][len(sanskrit.PREFIX):] for r in tdb.execute(
            f"SELECT DISTINCT lemma_key FROM {table} WHERE lemma_key LIKE 'san:%'")}
    # verbs (their preverbs can be stripped to find the root's entry)
    SAN_VERBS.update(r[0][len(sanskrit.PREFIX):] for r in tdb.execute(
        "SELECT DISTINCT lemma_key FROM morph WHERE lemma_key LIKE 'san:%' AND (pos LIKE 'verb%' OR pos LIKE "
        "'%participle%' OR pos LIKE 'absolutive%' OR pos LIKE 'gerundive%' OR pos LIKE 'infinitive%')"))
    # the DCS lemma ids the texts use, most frequent first: which homonym to gloss
    ids = {}
    if tdb.execute("SELECT 1 FROM sqlite_master WHERE name='san_lemma'").fetchone():
        for k, i, n in tdb.execute("SELECT lemma_key, lemma_id, n FROM san_lemma ORDER BY n DESC"):
            ids.setdefault(k[len(sanskrit.PREFIX):], []).append(i)
    tdb.close()
    if not lemmas:
        return
    wanted = {c for l in lemmas for c in sanskrit.candidates(l, l in SAN_VERBS)}
    credit = "Cologne Digital Sanskrit Dictionaries, Universität zu Köln (CC BY-SA 4.0)"
    for d, title, path, render, keep_all in (
            ("md", "A. A. Macdonell, A Practical Sanskrit Dictionary (1893)", md, sanskrit.md_html, True),
            ("mw", "M. Monier-Williams, A Sanskrit-English Dictionary (1899)", mw, sanskrit.mw_html, False)):
        if not os.path.exists(path):
            continue
        db.execute("INSERT INTO dictionary VALUES (?,?,?)", (d, title, credit))
        # consecutive records with the same headword make one entry (MW splits senses into records)
        run_k1, run = None, []

        def flush():
            if run_k1 is None or not run or (not keep_all and run_k1 not in wanted):
                return
            html_ = "".join(f"<p>{render(b)}</p>" if d == "mw" else render(b) for b in run)
            comp = zlib.compress(html_.encode("utf-8"), 9)[2:-4]
            db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                       (d, sanskrit.slp1_to_iast(run_k1), run_k1, run_k1, 1, comp))
            SAN_KEYS.add((d, run_k1))
            sizes[f"{d}_entries"] += 1
        for _, k1, body in sanskrit.iter_cologne(path):
            if k1 != run_k1:
                flush()
                run_k1, run = k1, []
            run.append(body)
        flush()
    if os.path.exists(dcs):
        rows = {}                    # word -> [(id, grammar, meanings)]
        with open(dcs, encoding="utf-8") as f:
            next(f)
            for line in f:
                c = line.rstrip("\n").split("\t")
                word = sanskrit.nfc(c[1]) if len(c) >= 5 else None
                if word in lemmas:
                    rows.setdefault(word, []).append((c[0], c[2], c[4]))
        for word, cands in rows.items():
            used = ids.get(word, [])
            # the homonym(s) the texts use, else the dictionary's first
            chosen = [r for i in used for r in cands if r[0] == i][:2] or cands[:1]
            for _, grammar, meanings in chosen:
                gloss = sanskrit.short_gloss(meanings)
                if gloss:
                    key = sanskrit.PREFIX + word
                    db.execute("INSERT INTO shortdef VALUES (?,?,?,?,?)", (key, key, word, gloss, grammar or None))
                    sizes["shortdefs_sanskrit"] += 1


def resolve_sanskrit(db, d, key):
    lemma = key[len(sanskrit.PREFIX):]
    if d == "short":
        hits = [r[0] for r in db.execute("SELECT rowid FROM shortdef WHERE key=?", (key,))]
        return hits, "exact" if hits else None
    for i, cand in enumerate(sanskrit.candidates(lemma, lemma in SAN_VERBS)):
        if (d, cand) in SAN_KEYS:
            hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict=? AND key=?", (d, cand))]
            if hits:
                return hits, "exact" if i == 0 else "alias"
    return [], None


OE_BT_KEYS = {}         # Old English lemma key -> Bosworth–Toller lookup spellings to try


def add_old_english(db, glossary_path, bt_json, sizes):
    """Klaeber's Beowulf glossary (default; its entries are the poem's lemmas)
    and Bosworth–Toller (Germanic Lexicon Project text, as parsed into entries
    by madeleineth/btc_anglo_saxon's parse_scanned_bt.py)."""
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", [
        ("klaeber", "Fr. Klaeber, Glossary to Beowulf (1922)", "Perseus Digital Library, Tufts University. CC BY-SA"),
        ("bt", "Bosworth & Toller, An Anglo-Saxon Dictionary (1898) and Supplement (1921)",
         "Germanic Lexicon Project (public domain); entries assembled by Madeleine Thompson's btc_anglo_saxon (MIT)"),
    ])
    if glossary_path:
        g = oldenglish.Glossary(glossary_path)
        for e in g.entries:
            comp = zlib.compress(e["html"].encode("utf-8"), 9)[2:-4]
            db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html,pos) VALUES (?,?,?,?,?,?,?)",
                       ("klaeber", oldenglish.display_headword(e["headword"]), e["key"], e["key"], 1, comp, e["pos"]))
            if e["gloss"] and not e["ref"]:
                db.execute("INSERT INTO shortdef VALUES (?,?,?,?,?)",
                           (e["key"], e["key"], oldenglish.display_headword(e["headword"]), e["gloss"], e["pos"]))
            hw = oldenglish.display_headword(e["headword"])
            variants = [oldenglish.ascify(hw.replace("(", "").replace(")", "")), oldenglish.ascify(hw)]
            variants += [oldenglish.ascify(a) for a in e["also"]]
            OE_BT_KEYS[e["key"]] = list(dict.fromkeys(v for v in variants if v))
            sizes["klaeber_entries"] += 1
    if bt_json:
        with open(bt_json, encoding="utf-8") as f:
            bt = json.load(f)
        defined = {r[0] for r in db.execute("SELECT key FROM shortdef WHERE key LIKE 'ang:%'")}
        for k, v in bt.items():
            hw = (v.get("headwords") or [k])[0]
            # a short definition for lemmas Klaeber doesn't gloss (the other poems' words)
            sk = oldenglish.PREFIX + oldenglish.form_key(hw)
            gloss = oldenglish.bt_gloss((v.get("defns") or [""])[0]) if sk not in defined else None
            if gloss:
                db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (sk, sk, hw, gloss))
                defined.add(sk)
                sizes["shortdefs_bt"] += 1
            for n, defn in enumerate(v.get("defns") or []):
                comp = zlib.compress(defn.encode("utf-8"), 9)[2:-4]
                db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                           ("bt", hw, k, k, n + 1, comp))
                sizes["bt_entries"] += 1


def oe_bt_candidates(key):
    """Spellings to try in Bosworth–Toller for a Klaeber lemma: Klaeber's own,
    then without ge-, and with the usual West Saxon / Anglian variants."""
    seen = []
    for k in OE_BT_KEYS.get(key) or [oldenglish.ascify(re.sub(r"\d+$", "", key[len(oldenglish.PREFIX):]))]:
        for v in (k, k[2:] if k.startswith("ge") and len(k) > 4 else None,
                  k.replace("io", "eo"), k.replace("y", "i"), k.replace("ie", "y"), k.replace("i", "y"),
                  k.replace("eo", "io"), k + k[-1] if k else None, k[:-1] if len(k) > 3 and k[-1] == k[-2] else None):
            if v and v not in seen:
                seen.append(v)
    return seen


def resolve_old_english(db, d, key):
    if d == "klaeber":
        hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict='klaeber' AND key=?", (key,))]
        return hits, "exact" if hits else None
    if d == "short":
        hits = [r[0] for r in db.execute("SELECT rowid FROM shortdef WHERE key=?", (key,))]
        return hits, "exact" if hits else None
    for n, cand in enumerate(oe_bt_candidates(key)):
        hits = [r[0] for r in db.execute("SELECT id FROM entry WHERE dict='bt' AND key=? ORDER BY homograph",
                                         (cand,))]
        if hits:
            return hits, "exact" if n == 0 else "alias"
    return [], None


ABBOTT_STRONG = {}      # Strong's number -> Abbott-Smith entry ids (NT lemmas MACULA spells differently)
NT_STRONG = {}          # NT lemma key -> Strong's number (from texts.db, table nt_strong)


def main(lsj_dir, ml_dir, shortdefs, texts_db, out, ccl_path=None, crum_path=None, autenrieth_path=None,
         abbott_path=None, ls_path=None, lewis_path=None, latin_shortdefs=None, klaeber_path=None, bt_json=None, hebrew_lexdir=None,
         sanskrit_sources=None):
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO dictionary VALUES (?,?,?)", [
        ("lsj", "Liddell–Scott–Jones, A Greek-English Lexicon (1940)",
         "Perseus Digital Library, Tufts University; Logeion edition by Helma Dik. CC BY-SA 4.0"),
        ("ml", "Liddell & Scott, An Intermediate Greek-English Lexicon (1889)",
         "Perseus Digital Library, Tufts University; Logeion edition by Helma Dik. CC BY-SA"),
    ])
    sizes = Counter()
    for kind, paths in (("lsj", glob.glob(f"{lsj_dir}/greatscott*.xml")),
                        ("ml", glob.glob(f"{ml_dir}/middleLiddell*.xml"))):
        seen = Counter()
        for hw, h in iter_entries(paths, kind):
            key = greek.lex_key(hw)
            seen[key] += 1
            raw = h.encode("utf-8")
            comp = zlib.compress(raw, 9)[2:-4]  # raw DEFLATE == Apple COMPRESSION_ZLIB
            sizes[f"{kind}_raw"] += len(raw)
            sizes[f"{kind}_deflate"] += len(comp)
            sizes[f"{kind}_entries"] += 1
            db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                       (kind, hw, key, greek.bare(hw), seen[key], comp))
    if autenrieth_path:
        db.execute("INSERT INTO dictionary VALUES (?,?,?)", (
            "aut", "Georg Autenrieth, A Homeric Dictionary (tr. R. P. Keep, 1891)",
            "Perseus Digital Library, Tufts University (Perseus:text:1999.04.0073). CC BY-SA 3.0"))
        seen = Counter()
        for hw, key, h in iter_autenrieth(autenrieth_path):
            seen[key] += 1
            comp = zlib.compress(h.encode("utf-8"), 9)[2:-4]
            db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                       ("aut", hw, key, greek.bare(key), seen[key], comp))
            sizes["aut_entries"] += 1
    abbott_glosses = []
    if abbott_path:
        db.execute("INSERT INTO dictionary VALUES (?,?,?)", (
            "abs", "G. Abbott-Smith, A Manual Greek Lexicon of the New Testament (1922)",
            "Marked up by the Abbott-Smith project (translatable-exegetical-tools); public domain"))
        seen = Counter()
        for hw, key, strong, gloss, h in iter_abbott(abbott_path):
            seen[key] += 1
            comp = zlib.compress(h.encode("utf-8"), 9)[2:-4]
            eid = db.execute("INSERT INTO entry(dict,headword,key,bare,homograph,html) VALUES (?,?,?,?,?,?)",
                             ("abs", hw, key, greek.bare(key), seen[key], comp)).lastrowid
            if strong:
                ABBOTT_STRONG.setdefault(strong, []).append(eid)
            if gloss:
                abbott_glosses.append((key, hw, gloss))
            sizes["abs_entries"] += 1
    global GREEK_DICTS
    GREEK_DICTS = ("lsj", "ml") + (("aut",) if autenrieth_path else ()) + (("abs",) if abbott_path else ()) \
        + ("short",)
    n = 0
    for line in open(shortdefs, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t", 1)
        if len(parts) == 2:
            db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (greek.lex_key(parts[0]), greek.bare(parts[0]), parts[0], parts[1]))
            n += 1
    sizes["shortdefs"] = n
    # Abbott-Smith's glosses as short definitions for NT words Logeion lacks
    have = {r[0] for r in db.execute("SELECT DISTINCT key FROM shortdef")}
    for key, hw, gloss in abbott_glosses:
        if key not in have:
            have.add(key)
            db.execute("INSERT INTO shortdef VALUES (?,?,?,?,NULL)", (key, greek.bare(key), hw, gloss))
            sizes["shortdefs_abbott"] += 1
    add_coptic(db, ccl_path, crum_path, sizes)
    add_latin(db, ls_path, lewis_path, latin_shortdefs, sizes)
    add_old_english(db, klaeber_path or None, bt_json or None, sizes)
    add_hebrew(db, hebrew_lexdir or None, sizes)
    add_sanskrit(db, sanskrit_sources or None, texts_db, sizes)
    db.commit()

    # ---- resolve every lemma used in the texts to entries, once, at build time
    tdb = sqlite3.connect(texts_db)
    if tdb.execute("SELECT 1 FROM sqlite_master WHERE name='nt_strong'").fetchone():
        NT_STRONG.update(tdb.execute("SELECT lemma_key, strong FROM nt_strong"))
    report = {"sizes": dict(sizes)}
    db.executescript(RESOLVE_SCHEMA)
    lemma_counts = Counter()
    per_work = {}
    for wid, title in tdb.execute("SELECT id, title FROM work"):
        rows = tdb.execute("SELECT t.lemma_key FROM token t JOIN segment s ON s.id=t.segment_id "
                           "WHERE s.work_id=?", (wid,)).fetchall()
        per_work[title] = Counter(r[0] for r in rows if r[0])
        lemma_counts.update(per_work[title])
    # alternative analyses (Morpheus) can open other lemmas too
    alternatives = {r[0] for r in tdb.execute("SELECT DISTINCT lemma_key FROM analysis") if r[0]}
    # …and so can the other morphemes of a Coptic bound group
    alternatives |= {r[0] for r in tdb.execute("SELECT DISTINCT lemma_key FROM morph") if r[0]}
    found = {}
    for key in set(lemma_counts) | alternatives:
        for d in dicts_for(key):
            hits, how = resolve(db, d, key)
            for target in hits:
                db.execute("INSERT INTO resolve VALUES (?,?,?,?)", (key, d, target, how or "exact"))
            found[(key, d)] = how if hits else None
    db.commit()
    for title, counts in per_work.items():
        total = sum(counts.values())
        cov, misses = {}, {}
        coptic_work = any(coptic.is_coptic(k) for k in counts)
        oe_work = sum(1 for k in counts if oldenglish.is_old_english(k)) > len(counts) / 2
        heb_work = sum(1 for k in counts if hebrew.is_hebrew_key(k)) > len(counts) / 2
        san_work = sum(1 for k in counts if sanskrit.is_sanskrit_key(k)) > len(counts) / 2
        latin_work = not oe_work and sum(1 for k in counts if latin.is_latin(k)) > len(counts) / 2
        for d in (("short", "ccl", "crum") if coptic_work else ("short", "bdb", "strong") if heb_work
                  else ("short", "md", "mw") if san_work
                  else ("short", "klaeber", "bt") if oe_work
                  else ("short", "ls", "lewis") if latin_work else ("short",) + GREEK_DICTS[:-1]):
            by = Counter()
            miss = Counter()
            for key, n in counts.items():
                how = found.get((key, d))
                by[how or "missing"] += n
                if not how:
                    miss[key] += n
            cov[d] = {k: round(100 * v / total, 2) for k, v in by.items()}
            misses[d] = miss.most_common(12)
        report[title] = dict(tokens_with_lemma=total, coverage_pct=cov, top_misses=misses)
    db.execute("VACUUM")
    db.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


GREEK_DICTS = ("lsj", "ml", "short")
LATIN_DICTS = ("ls", "lewis", "short")


def latin_candidates(key):
    """Lemma conventions differ: deponents (Morpheus 'loquor', some
    dictionaries list the -or form), -que/-ve/-ne left on, 'Iesus'/'Jesus'."""
    yield key
    for enc in ("que", "ue", "ne"):
        if key.endswith(enc) and len(key) > len(enc) + 2:
            yield key[: -len(enc)]
    if key.endswith("or"):
        yield key[:-2] + "o"
    if key.endswith("o"):
        yield key[:-1] + "or"


def dicts_for(key):
    if sanskrit.is_sanskrit_key(key):
        return ("md", "mw", "short")
    if hebrew.is_hebrew_key(key):
        return ("bdb", "strong", "short")
    if oldenglish.is_old_english(key):
        return ("klaeber", "bt", "short")
    if coptic.is_coptic(key):
        return ("ccl", "crum", "short")
    if latin.is_latin(key):
        return LATIN_DICTS
    return GREEK_DICTS


if __name__ == "__main__":
    main(*sys.argv[1:17])
