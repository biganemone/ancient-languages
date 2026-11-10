"""Build grammar.db: reference grammars as numbered sections, and the
sections a word's parse points to.

Sources (public domain books, in sources/grammars/; see README):
  smyth.xml   Smyth, A Greek Grammar for Colleges (1920)       Perseus:text:1999.04.0007 (TEI download)
  monro.xml   Monro, A Grammar of the Homeric Dialect (1891)   written by fetch_monro.py from
              Dickinson College Commentaries (Perseus does not have it; optional)

The app's lookup card turns a parse ("verb · aorist · indicative · active …")
into keys ("tense:aorist", "mood:indicative", "augment" …); the `ref` table
maps those keys to sections. Each rule below names the section number we
expect and words its opening should contain: the build looks near that number
for a section that matches, so a wrong guess is corrected (or reported in the
report's "missing" list) rather than silently pointing at the wrong page.

Usage: python build_grammar.py <sources/grammars> <out grammar.db>   (report on stdout)
"""
import copy
import unicodedata
import html
import json
import os
import re
import sqlite3
import sys

from lxml import etree

import greek

PARSER = etree.XMLParser(recover=True)

GRAMMARS = [
    # id, file, title, short name, credit, the TEI division types that are its numbered sections
    ("smyth", "smyth.xml", "A Greek Grammar for Colleges", "Smyth",
     "Herbert Weir Smyth, A Greek Grammar for Colleges (1920). Text: Perseus Digital Library (CC BY-SA).",
     {"smythp"}),
    ("monro", "monro.xml", "A Grammar of the Homeric Dialect", "Monro",
     "D. B. Monro, A Grammar of the Homeric Dialect, 2nd ed. (1891). Text: Dickinson College Commentaries, ed. Meagan Ayer and Seth Levin (CC BY-SA 4.0).",
     {"section"}),
]

# key, grammar, expected section (None: the first match anywhere), words the
# section's opening must contain (regex), label in the app
RULES = [
    # forms
    ("augment", "smyth", 428, r"augment", "The augment"),
    ("reduplication", "smyth", 439, r"reduplicat", "Reduplication"),
    ("endings:verb", "smyth", 462, r"ending", "Personal endings"),
    ("aorist2", "smyth", 546, r"second aorist is formed", "The second aorist"),
    ("degree", "smyth", 313, r"compar", "Comparison of adjectives"),
    ("forms:article", "smyth", 332, r"article", "The article: forms"),
    ("forms:numeral", "smyth", 347, r"numer|cardinal", "Numerals"),
    # syntax: tenses
    ("tense:present", "smyth", 1875, r"present", "The present"),
    ("tense:imperfect", "smyth", 1889, r"imperfect", "The imperfect"),
    ("tense:future", "smyth", 1910, r"future", "The future"),
    ("tense:aorist", "smyth", 1923, r"aorist", "The aorist"),
    ("tense:perfect", "smyth", 1945, r"perfect", "The perfect"),
    ("tense:pluperfect", "smyth", 1952, r"pluperfect", "The pluperfect"),
    ("tense:future perfect", "smyth", 1955, r"future perfect", "The future perfect"),
    # moods
    ("mood:indicative", "smyth", 1770, r"indicative", "The indicative"),
    ("mood:subjunctive", "smyth", 1795, r"subjunctive", "The subjunctive"),
    ("mood:optative", "smyth", 1814, r"optative", "The optative"),
    ("mood:imperative", "smyth", 1835, r"imperative", "The imperative"),
    ("mood:infinitive", "smyth", 1966, r"infinitive", "The infinitive"),
    ("mood:participle", "smyth", 2039, r"participle", "The participle"),
    # voices
    ("voice:active", "smyth", 1703, r"active", "The active voice"),
    ("voice:middle", "smyth", 1713, r"middle", "The middle voice"),
    ("voice:passive", "smyth", 1735, r"passive", "The passive voice"),
    # cases
    ("case:nominative", "smyth", 938, r"nominative", "The nominative"),
    ("case:vocative", "smyth", 1283, r"vocative", "The vocative"),
    ("case:genitive", "smyth", 1289, r"genitive", "The genitive"),
    ("case:dative", "smyth", 1450, r"dative", "The dative"),
    ("case:accusative", "smyth", 1551, r"accusative", "The accusative"),
    # parts of speech
    ("pos:article", "smyth", 1099, r"article", "The article: uses"),
    ("pos:pronoun", "smyth", 1190, r"pronoun", "Pronouns"),
    ("pos:adjective", "smyth", 1018, r"adjective", "Adjectives"),
    ("pos:preposition", "smyth", 1636, r"preposition", "Prepositions"),
    ("pos:particle", "smyth", 2769, r"particle", "Particles"),
    ("pos:conjunction", "smyth", 2163, r"co-?ordinat|conjunction", "Conjunctions"),
    ("pos:adverb", "smyth", 341, r"adverb", "Adverbs"),
    # Homer (Monro, as fetch_monro.py numbers it). Forms first, then use, where
    # Monro treats them apart (the subjunctive's forms in §80, its uses from §274).
    ("endings:verb", "monro", 3, r"personal endings", "Personal endings in Homer"),
    ("reduplication", "monro", 23, r"reduplication", "Reduplication in Homer"),
    ("aorist2", "monro", 31, r"thematic aorist|weak form", "The thematic (second) aorist in Homer"),
    ("tense:future", "monro", 63, r"future", "The future in Homer"),
    ("augment", "monro", 67, r"augment", "The augment in Homer"),
    ("augment", "monro", 69, r"loss of augment", "Augment dropped in Homer"),
    ("tense:pluperfect", "monro", 68, r"pluperfect", "The pluperfect in Homer"),
    ("tense:perfect", "monro", 28, r"perfect", "Meaning of the perfect in Homer"),
    ("tense:present", "monro", 70, r"present stem", "Meaning of the present stem in Homer"),
    ("tense:imperfect", "monro", 70, r"present stem", "Meaning of the present stem in Homer"),
    ("tense:aorist", "monro", 75, r"aorist", "Meaning of the aorist in Homer"),
    ("mood:subjunctive", "monro", 80, r"subjunctive", "Forms of the subjunctive in Homer"),
    ("mood:subjunctive", "monro", 274, r"subjunctive", "The subjunctive in Homer"),
    ("mood:optative", "monro", 83, r"optative", "Forms of the optative in Homer"),
    ("mood:optative", "monro", 299, r"optative", "The optative in Homer"),
    ("mood:indicative", "monro", 323, r"indicative", "The indicative in Homer"),
    ("mood:imperative", "monro", 327, r"imperative", "The imperative in Homer"),
    ("mood:infinitive", "monro", 231, r"infinitive", "The infinitive in Homer"),
    ("mood:participle", "monro", 243, r"participle", "The participle in Homer"),
    ("case:nominative", "monro", 161, r"nominative", "The nominative in Homer"),
    ("case:vocative", "monro", 164, r"vocative", "The vocative in Homer"),
    ("case:accusative", "monro", 132, r"accusative", "The accusative in Homer"),
    ("case:dative", "monro", 142, r"dative", "The dative in Homer"),
    ("case:genitive", "monro", 146, r"genitive", "The genitive in Homer"),
    ("degree", "monro", 121, r"comparison|comparative", "Comparison in Homer"),
    ("forms:numeral", "monro", 130, r"numeral", "Numerals in Homer"),
    ("pos:preposition", "monro", 174, r"preposition", "Prepositions in Homer"),
    ("pos:pronoun", "monro", 247, r"pronoun", "Pronouns in Homer"),
    ("pos:article", "monro", 256, r"article", "The article in Homer"),
    ("forms:article", "monro", 256, r"article", "The article in Homer"),
    ("pos:particle", "monro", 329, r"particle", "Particles in Homer"),
]
WINDOW = 60     # how far from the expected number to look

SCHEMA = """
CREATE TABLE grammar (id TEXT PRIMARY KEY, title TEXT, short TEXT, credit TEXT, language TEXT);
CREATE TABLE section (grammar TEXT, seq INT, n TEXT, num INT, heading TEXT, path TEXT, html TEXT, plain TEXT,
  label TEXT, PRIMARY KEY (grammar, n));
CREATE INDEX section_seq ON section(grammar, seq);
CREATE TABLE ref (key TEXT, grammar TEXT, n TEXT, label TEXT, ord INT);
CREATE INDEX ref_key ON ref(key);
CREATE TABLE verb (key TEXT, grammar TEXT, headword TEXT, n TEXT, anchor TEXT);
CREATE INDEX verb_key ON verb(key);
"""

BETA_WORD = re.compile(r"[A-Za-z*()/\\=+|_^'0-9]+")
HAS_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")


def local(e):
    return etree.QName(e).localname if isinstance(e.tag, str) else ""


def greek_text(text):
    """Perseus's Greek: Beta Code (as in Autenrieth), unless already Unicode."""
    if not text or HAS_GREEK.search(text):
        return text or ""
    return BETA_WORD.sub(lambda m: greek.from_beta(m.group(), quantity=True), text)


def is_greek(e):
    return (e.get("lang") or e.get("{http://www.w3.org/XML/1998/namespace}lang") or "") in ("greek", "grc", "gr")


def section_target(e):
    """A cross-reference's section: "s428", "s429a", n="124 D." -> "428", "429", "124".
    Sub-notes (429 a, 124 D) are part of their section here, so the number is enough."""
    m = re.search(r"\d+", e.get("target") or e.get("n") or "")
    return m.group() if m else None


def to_html(div, units, gid):
    """One section's TEI -> small HTML, leaving out sections nested inside it."""
    out = []

    def tail(e, gk):
        if e.tail and e is not div:
            out.append(html.escape(greek_text(e.tail) if gk else e.tail))

    def rec(e, gk=False):
        name = local(e)
        if not name:                 # comments, processing instructions
            tail(e, gk)
            return
        if e is not div and name.startswith("div") and (e.get("type") or "").lower() in units:
            return                   # a section of its own (its tail belongs to us, but is whitespace)
        g = gk or is_greek(e)
        rend = (e.get("rend") or "").lower()
        open_, close = "", ""
        if name == "label":
            out.append(f'<b class="sub">{html.escape(e.text or "")}</b> ')
            tail(e, gk)
            return
        if name in ("pb", "milestone", "figure"):
            tail(e, gk)
            return
        if name == "lb":
            out.append("<br>")
            tail(e, gk)
            return
        if name == "gap":
            out.append("…")
            tail(e, gk)
            return
        if name == "head":
            open_, close = ("<h4>", "</h4>")
        elif name == "p":
            open_, close = (f'<p id="{e.get("id")}">' if e.get("id") else "<p>"), "</p>"
        elif name == "bibl" and (e.get("n") or "").startswith("LSJ"):
            tail(e, gk)          # Perseus's link to the LSJ entry: "LSJ" at the end of each verb
            return
        elif name == "foreign" and g:
            bold = "bold" in rend
            open_, close = ('<b class="gk">', "</b>") if bold else ('<span class="gk">', "</span>")
        elif name in ("hi", "emph", "title", "term", "mentioned"):
            if "bold" in rend:
                open_, close = "<b>", "</b>"
            elif "small" in rend or "caps" in rend:
                open_, close = '<span class="sc">', "</span>"
            else:
                open_, close = "<i>", "</i>"
        elif name in ("list",):
            open_, close = "<ul>", "</ul>"
        elif name in ("item",):
            open_, close = "<li>", "</li>"
        elif name == "table":
            open_, close = "<table>", "</table>"
        elif name == "row":
            open_, close = "<tr>", "</tr>"
        elif name == "cell":
            open_, close = "<td>", "</td>"
        elif name in ("quote", "q"):
            open_, close = "<q>", "</q>"
        elif name in ("bibl", "cit"):
            open_, close = '<span class="bibl">', "</span>"
        elif name == "note":
            open_, close = '<span class="fn">[', "]</span>"
        elif name == "ref" and section_target(e):
            open_, close = f'<a href="grammar://{gid}/{section_target(e)}">', "</a>"
        out.append(open_)
        if e.text:
            out.append(html.escape(greek_text(e.text) if g else e.text))
        for c in e:
            rec(c, g)
        out.append(close)
        tail(e, gk)

    rec(div)
    body = re.sub(r"[ \t\r\n]+", " ", "".join(out)).strip()
    return body


def plain_text(div, units):
    """The section's own words (no nested sections), Greek converted: for search and rules."""
    parts = []

    def rec(e, gk=False):
        if not local(e):
            return
        if e is not div and local(e).startswith("div") and (e.get("type") or "").lower() in units:
            return
        g = gk or is_greek(e)
        if e.text:
            parts.append(greek_text(e.text) if g else e.text)
        for c in e:
            rec(c, g)
            if local(c) in ("cell", "row", "p", "label", "item", "head", "lb"):
                parts.append(" ")
            if c.tail:
                parts.append(greek_text(c.tail) if g else c.tail)

    rec(div)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def own_head(div):
    h = next((c for c in div if local(c) == "head"), None)
    return tidy_head(plain_text(h, ())) if h is not None else ""


ROMAN = re.compile(r"^[IVXL]+\.?$")


def tidy_head(text):
    """ "INDICATIVE WITHOUT ἄν" -> "Indicative without ἄν", "IV. SECOND AORIST SYSTEM" ->
    "IV. Second aorist system": Smyth sets many headings in capitals."""
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    latin = re.sub(r"[^A-Za-z]", "", text)
    if len(latin) < 3 or not latin.isupper():
        return text
    words, out, first = text.split(" "), [], True
    for w in words:
        if ROMAN.match(w) or not re.search(r"[A-Z]", w):
            out.append(w)          # numerals, Greek, punctuation
            continue
        w = w.lower()
        out.append(w[:1].upper() + w[1:] if first else w)
        first = False
    return " ".join(out)


def trail_of(e, units):
    """The headings of the divisions around e, outermost first (at most two)."""
    trail = []
    for a in e.iterancestors():
        if local(a).startswith("div") and (a.get("type") or "").lower() not in units:
            h = own_head(a)
            if h:
                trail.append(h)
    return " › ".join(reversed(trail[:2]))


def sections(path, units):
    """(n, heading, path, element) for each numbered section, in book order.

    Two encodings: numbered divisions (<div3 type="section" n="161">, as
    fetch_monro.py writes) or milestones between paragraphs (<milestone
    unit="smythp" n="428"/>, Perseus's Smyth). For milestones the section is
    gathered into a new <div> from the siblings up to the next milestone,
    heading or division; sub-notes ("429 a", "430 D") join their section
    under a bold label rather than becoming sections of their own."""
    root = etree.parse(path, PARSER).getroot()
    body = next(root.iter("body", "{http://www.tei-c.org/ns/1.0}body"), root)
    marks = [m for m in body.iter() if local(m) == "milestone"
             and (m.get("unit") or "").lower() in units and m.get("n")]
    if not marks:
        out = []
        for e in body.iter():
            if local(e).startswith("div") and (e.get("type") or "").lower() in units and e.get("n"):
                out.append((e.get("n").strip(), own_head(e) or tidy_head(e.get("heading") or ""),
                            trail_of(e, units), e))
        return out

    def is_mark(e):
        return local(e) == "milestone" and (e.get("unit") or "").lower() in units

    def heads_next_section(head):
        """A heading that introduces the next section (rather than a sub-heading
        inside this one) is followed directly by its milestone."""
        nxt = head.getnext()
        while nxt is not None and local(nxt) in ("pb", "head", ""):
            nxt = nxt.getnext()
        return nxt is not None and is_mark(nxt)

    out = []
    for m in marks:
        n = m.get("n").strip()
        base = re.match(r"\d+", n)
        if not base:
            continue
        base = base.group()
        sub = n[len(base):].strip(" .,")
        if sub and out and out[-1][0] == base:
            div = out[-1][3]
        else:
            div = etree.Element("div", type="section", n=base)
            heading = ""
            prev = m.getprevious()
            while prev is not None and local(prev) in ("pb", ""):
                prev = prev.getprevious()
            if prev is not None and local(prev) == "head":
                heading = tidy_head(plain_text(prev, ()))
            out.append((base, heading, trail_of(m, units), div))
        first = True
        for sib in m.itersiblings():
            name = local(sib)
            if is_mark(sib) or name.startswith("div"):
                break
            if name == "head" and heads_next_section(sib):
                break
            if not name:
                continue
            c = copy.deepcopy(sib)
            c.tail = sib.tail
            if first and sub:
                label = etree.Element("label")
                label.text = sub + "."
                if name == "p":
                    label.tail = c.text
                    c.text = None
                    c.insert(0, label)
                else:
                    div.append(label)
            div.append(c)
            first = False
    return out


def fallback_heading(plain):
    """A section without a heading: its run-in title ("Syllabic Augment.—…"),
    else its opening words."""
    text = re.sub(r"^\s*\d+[a-z]?\.?\s*", "", plain)
    m = re.match(r"(.{3,60}?)\.?\s*—", text)
    if m and "." not in m.group(1).rstrip(".")[-1:]:
        return m.group(1).rstrip(".")
    if len(text) <= 70:
        return text
    return text[:70].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def greek_key(word):
    """βαρῡ́νω, "-βαίνω", λέγω2 -> βαρυνω, βαινω, λεγω: no accents, breathings, quantity
    or digits, final sigma as σ. The app makes lemmas into keys the same way."""
    d = unicodedata.normalize("NFD", word)
    return "".join(c for c in d if unicodedata.category(c)[0] == "L").lower().replace("ς", "σ")


def appendix_pages(path, units):
    """Divisions with no numbered sections, in a part with none: Smyth's
    appendix, the List of Verbs ("Verbs beginning with β" ...). Each becomes
    an unnumbered page ("verbs-β", label "Verbs: β"), and each paragraph an
    entry, indexed by its headword (the first Greek word) for the lookup card.
    -> [(n, heading, path, div, label, [(headword, anchor)])]"""
    root = etree.parse(path, PARSER).getroot()
    body = next(root.iter("body", "{http://www.tei-c.org/ns/1.0}body"), root)

    def numbered(e):
        return any((local(m) == "milestone" or (local(m).startswith("div") and m.get("n")))
                   and (m.get("unit") or m.get("type") or "").lower() in units for m in e.iter())

    out = []
    for part in body:
        if not local(part).startswith("div") or numbered(part):
            continue
        part_head = own_head(part)
        for d in part:
            if not local(d).startswith("div"):
                continue
            heading = own_head(d).replace("ς", "σ")           # Beta Code s at a word's end
            letter = heading.split()[-1] if heading else str(len(out) + 1)
            page = etree.Element("div", type="appendix")
            entries = []
            for c in d:
                if local(c) in ("head", "pb", ""):
                    continue
                c = copy.deepcopy(c)
                if local(c) == "p":
                    first = next((f for f in c.iter() if local(f) == "foreign" and is_greek(f)), None)
                    word = greek_text("".join(first.itertext())) if first is not None else ""
                    word = re.split(r"[,\s(]", word.strip().lstrip("-"), maxsplit=1)[0].replace("-", "")
                    if word:
                        anchor = f"v{len(entries) + 1}"
                        c.set("id", anchor)
                        entries.append((word, anchor))
                page.append(c)
            label = "Verbs: " + letter if "verb" in part_head.lower() else heading
            out.append(("verbs-" + letter if "verb" in part_head.lower() else f"appendix-{len(out) + 1}",
                        heading, part_head.replace("Appendix: ", ""), page, label, entries))
    return out


def num(n):
    m = re.match(r"\d+", n)
    return int(m.group()) if m else None


def resolve(rule, rows):
    """The section a rule points to: near the expected number, the nearest
    whose heading or opening words match."""
    _, _, expected, pattern, _ = rule
    rx = re.compile(pattern, re.I)
    candidates = []
    for n, heading, plain in rows:
        k = num(n)
        if expected is not None and (k is None or abs(k - expected) > WINDOW):
            continue
        opening = (heading + " " + plain[:200])
        if rx.search(opening):
            candidates.append((abs((k or 0) - expected) if expected is not None else 0,
                               0 if rx.search(heading) else 1, n))
    if not candidates:
        return None
    if expected is None:   # the first (heading matches preferred), in book order
        heads = [c for c in candidates if c[1] == 0]
        return (heads or candidates)[0][2]
    return min(candidates)[2]


def main(src, out):
    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    report = {"grammars": {}, "refs": {}, "missing": [], "moved": []}
    built = set()
    for gid, fname, title, short, credit, units in GRAMMARS:
        path = os.path.join(src, fname)
        if not os.path.exists(path):
            report["grammars"][gid] = "not found: " + path
            continue
        # book order: DCC's menu (Monro) lists a few topics out of sequence
        secs = sorted(sections(path, units), key=lambda t: num(t[0]) or 0)
        pages = appendix_pages(path, units)
        rows = []
        seen = set()
        for seq, (n, heading, trail, el) in enumerate(secs):
            if n in seen:
                continue
            seen.add(n)
            plain = plain_text(el, units)
            heading = heading or fallback_heading(plain)
            db.execute("INSERT INTO section VALUES (?,?,?,?,?,?,?,?,?)",
                       (gid, seq, n, num(n), heading, trail, to_html(el, units, gid), plain, "§" + n))
            rows.append((n, heading, plain))
        for k, (n, heading, trail, el, label, entries) in enumerate(pages):
            db.execute("INSERT INTO section VALUES (?,?,?,?,?,?,?,?,?)",
                       (gid, len(secs) + k, n, None, heading, trail, to_html(el, units, gid),
                        plain_text(el, units), label))
            db.executemany("INSERT INTO verb VALUES (?,?,?,?,?)",
                           [(greek_key(hw), gid, hw, n, anchor) for hw, anchor in entries])
        if pages:
            report["appendix"] = report.get("appendix", {})
            report["appendix"][gid] = f"{len(pages)} pages, {sum(len(p[5]) for p in pages)} entries"
        db.execute("INSERT INTO grammar VALUES (?,?,?,?,?)", (gid, title, short, credit, "grc"))
        report["grammars"][gid] = f"{len(rows)} sections"
        if rows:
            built.add(gid)
        for i, rule in enumerate(r for r in RULES if r[1] == gid):
            key, _, expected, _, label = rule
            n = resolve(rule, rows)
            if n is None:
                report["missing"].append(f"{gid} {key} (expected near {expected})")
                continue
            if expected is not None and n != str(expected):
                report["moved"].append(f"{gid} {key}: expected {expected}, using {n}")
            db.execute("INSERT INTO ref VALUES (?,?,?,?,?)", (key, gid, n, label, i))
            report["refs"][f"{gid} {key}"] = n
    db.commit()
    db.execute("VACUUM")
    db.close()
    if not built:
        os.remove(out)
        report["note"] = "no grammar sources found; grammar.db not built"
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
