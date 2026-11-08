"""Coptic helpers: lookup keys, Coptic SCRIPTORIUM tags, and readers for the
two Coptic dictionaries.

  - Comprehensive Coptic Lexicon (KELLIA: BBAW + DDGLC), CC BY-SA 4.0
  - Crum, A Coptic Dictionary (1939), as digitised in Marcion (Milan
    Konvicka, GPL v2), table dumps `coptwrd` (words) + `coptdrv` (derivations)
"""
import bz2
import html
import re
import unicodedata

from lxml import etree

import marcion

TEI = {"t": "http://www.tei-c.org/ns/1.0"}


def is_coptic(s):
    return any("Ⲁ" <= ch <= "⳿" or "Ϣ" <= ch <= "ϯ" for ch in s or "")


def key(s):
    """Lookup key: Coptic letters only (no strokes, hyphens, ⸗, parentheses)."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if "Ⲁ" <= ch <= "⳿" or "Ϣ" <= ch <= "ϯ")
    return unicodedata.normalize("NFC", s).lower()


# Lemmas as the NLP tools give them for non-Sahidic (mostly Lycopolitan)
# spellings, mapped to the Sahidic headword the dictionaries use. Drawn from
# the commonest misses in the Nag Hammadi texts.
VARIANTS = {
    "ⲁⲃⲁⲗ": "ⲉⲃⲟⲗ", "ⲡⲉⲓ": "ⲡⲁⲓ", "ⲙⲙⲁ": "ⲙⲙⲟ", "ϩⲣⲏⲓ": "ϩⲣⲁⲓ", "ⲁϩⲣⲏⲓ": "ⲉϩⲣⲁⲓ",
    "ⲉⲉⲓ": "ⲉⲓ", "ⲛⲉⲩⲙⲁ": "ⲡⲛⲉⲩⲙⲁ", "ⲟⲩⲁⲉⲉⲧ": "ⲟⲩⲁⲁⲧ", "ⲥⲁⲩⲛⲉ": "ⲥⲟⲟⲩⲛ", "ⲧⲣⲟⲩ": "ⲧⲏⲣ",
    "ⲛⲙⲙⲉ": "ⲛⲙⲙⲁ", "ϣⲉϫⲉ": "ϣⲁϫⲉ", "ⲙⲙⲁⲛ": "ⲙⲙⲟⲛ", "ⲟⲩⲁⲛϩ": "ⲟⲩⲱⲛϩ", "ⲟⲩⲁⲉⲓⲛ": "ⲟⲩⲟⲉⲓⲛ",
    "ⲛⲛⲁϩⲣⲛ": "ⲛⲁϩⲣⲛ", "ⲛⲁϭ": "ⲛⲟϭ", "ⲧⲙⲏⲉ": "ⲙⲉ", "ⲙⲏⲉ": "ⲙⲉ", "ⲟⲩⲁⲉⲓϣ": "ⲟⲩⲟⲉⲓϣ",
    "ⲛϭⲁⲙ": "ϭⲟⲙ", "ϭⲁⲙ": "ϭⲟⲙ", "ⲙⲉⲩ": "ⲙⲁⲩ", "ϩⲙⲁⲧ": "ϩⲙⲟⲧ", "ⲧⲱⲱⲛ": "ⲧⲱⲛ",
    "ϫⲁⲉⲓⲥ": "ϫⲟⲉⲓⲥ", "ⲧⲥⲁⲣⲁⲝ": "ⲥⲁⲣⲝ", "ⲥⲁⲣⲁⲝ": "ⲥⲁⲣⲝ", "ⲟⲩⲙⲛⲧϫⲁⲉⲓⲥ": "ⲙⲛⲧϫⲟⲉⲓⲥ",
    "ⲙⲛⲧϫⲁⲉⲓⲥ": "ⲙⲛⲧϫⲟⲉⲓⲥ", "ϫⲁⲥⲉ": "ϫⲟⲥⲉ", "ⲟⲩϫⲉⲉⲓ": "ⲟⲩϫⲁⲓ", "ⲓⲛⲉ": "ⲉⲓⲛⲉ", "ⲉϩⲏ": "ϩⲏ",
    "ⲥⲁⲩⲛ": "ⲥⲟⲟⲩⲛ", "ⲁⲣⲁ": "ⲉⲣⲟ", "ⲛⲧⲁϥ": "ⲛⲧⲟϥ", "ⲁⲛⲁⲕ": "ⲁⲛⲟⲕ",
    "ⲙⲁⲉⲓⲉ": "ⲙⲉ", "ϩⲁⲩⲛ": "ϩⲟⲩⲛ", "ⲁϩⲟⲩⲛ": "ⲉϩⲟⲩⲛ",
}


def spelling_variants(k):
    """Other spellings to try: the dialect table, then Greek ι/ει (itacism)."""
    if k in VARIANTS:
        yield VARIANTS[k]
    if "ⲉⲓ" in k:
        yield k.replace("ⲉⲓ", "ⲓ")
    elif "ⲓ" in k:
        yield re.sub(r"(?<!ⲉ)ⲓ", "ⲉⲓ", k)


# Coptic SCRIPTORIUM part-of-speech tags (Sahidic tag set)
POS = {
    "N": "noun", "NPROP": "proper noun", "V": "verb", "VBD": "verb (with object)",
    "VSTAT": "stative verb", "VIMP": "imperative", "ADV": "adverb", "NUM": "numeral",
    "ART": "article", "PPOS": "possessive article", "PDEM": "demonstrative",
    "PINT": "interrogative pronoun", "PPERS": "personal pronoun (subject)",
    "PPERO": "personal pronoun (object)", "PPERI": "independent personal pronoun",
    "PREP": "preposition", "CONJ": "conjunction", "PTC": "particle", "NEG": "negation",
    "COP": "copula", "EXIST": "existential (there is/are)", "IMOD": "interrogative modifier",
    "FUT": "future auxiliary", "CREL": "relative converter", "CCIRC": "circumstantial converter",
    "CFOC": "focalising converter", "CPRET": "preterite converter",
    "APST": "past (perfect) auxiliary", "AAOR": "aorist auxiliary", "ACONJ": "conjunctive",
    "ACOND": "conditional", "AJUS": "jussive", "ACAUS": "causative infinitive",
    "AOPT": "optative", "APREC": "precursive", "ALIM": "limitative", "ANY": "'not yet'",
    "ANEGPST": "negative past", "ANEGAOR": "negative aorist", "ANEGOPT": "negative optative",
    "ANEGJUS": "negative jussive", "AFUTCONJ": "future conjunctive", "FM": "foreign word",
    "PUNCT": "punctuation", "UNKNOWN": "unknown",
}
CONTENT = ["N", "V", "VBD", "VSTAT", "VIMP", "NPROP", "ADV", "NUM", "PDEM", "PINT", "PREP"]


def describe_pos(tag):
    return " + ".join(POS.get(t, t) for t in (tag or "").split("_"))


# ------------------------------------------------- Comprehensive Coptic Lexicon --
CCL_POS = {"Subst.": "noun", "Vb.": "verb", "Adj.": "adjective", "Adv.": "adverb",
           "Präp.": "preposition", "Konj.": "conjunction", "Partikel": "particle",
           "Zahlzeichen": "numeral", "Zahlwort": "numeral", "Verbalpräfix": "verbal prefix",
           "Nominalpräfix": "nominal prefix", "Satzkonverter": "converter",
           "Pronomen": "pronoun", "Interjektion": "interjection",
           "unbestimmter Artikel": "indefinite article", "bestimmter Artikel": "definite article",
           "Personalpronomen": "personal pronoun"}
GENDER = {"m.": "masc.", "f.": "fem.", "m./f.": "masc./fem."}


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def read_ccl(path):
    """Yield (headword, [lookup keys, lemma first], html, gloss, part of speech)."""
    root = etree.parse(path).getroot()
    for entry in root.iterfind(".//t:entry", TEI):
        forms = entry.findall("t:form", TEI)
        lemma_form = next((f for f in forms if f.get("type") == "lemma"), forms[0] if forms else None)
        if lemma_form is None:
            continue
        headword = _text(lemma_form.find("t:orth", TEI))
        keys = []
        for f in [lemma_form] + forms:
            if "deprecated" in (f.get("change") or ""):
                continue
            k = key(_text(f.find("t:orth", TEI)))
            if k and k not in keys:
                keys.append(k)
        pos = _text(entry.find(".//t:gramGrp/t:pos", TEI))
        gen = _text(entry.find(".//t:gramGrp/t:gen", TEI))
        # forms by dialect: S ⲁ-, ⲁ⸗; B …
        by_dialect = {}
        for f in forms:
            if "deprecated" in (f.get("change") or ""):
                continue
            d = _text(f.find("t:usg", TEI)) or "?"
            o = _text(f.find("t:orth", TEI))
            if o and o not in by_dialect.setdefault(d, []):
                by_dialect[d].append(o)
        senses, gloss, crum_refs = [], None, []
        for i, sense in enumerate(entry.iterfind("t:sense", TEI), 1):
            en = [_text(q) for q in sense.iterfind(".//t:quote", TEI) if q.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"]
            de = [_text(q) for q in sense.iterfind(".//t:quote", TEI) if q.get("{http://www.w3.org/XML/1998/namespace}lang") == "de"]
            bibl = "; ".join(_text(b) for b in sense.iterfind(".//t:bibl", TEI))
            crum_refs += re.findall(r"\bCD (\d+[ab]?)", bibl)
            text = "; ".join(x for x in en if x) or "; ".join(x for x in de if x)
            if text and gloss is None:
                gloss = text
            if text:
                senses.append(f'<div class="sense l1"><b class="sn">{i}.</b> {html.escape(text)}'
                              + (f' <span class="bibl">{html.escape(bibl)}</span>' if bibl else "") + "</div>")
        head = (f'<b class="hw cop">{html.escape(headword)}</b>'
                + (f' <i>{html.escape(CCL_POS.get(pos, pos))}</i>' if pos else "")
                + (f' <i>{html.escape(GENDER.get(gen, gen))}</i>' if gen else ""))
        dialects = " · ".join(f'<span class="au">{html.escape(d)}</span> <span class="cop">{html.escape(", ".join(v))}</span>'
                              for d, v in by_dialect.items())
        body = head + (f'<div class="forms">{dialects}</div>' if dialects else "") + "".join(senses)
        yield headword, keys, body, gloss, CCL_POS.get(pos, pos or None)


# ------------------------------------------------------------------- Crum --
GREEK = dict(zip("abgdezhqiklmnjoprstufxcw", "αβγδεζηθικλμνξοπρστυφχψω"))


def ascii_greek(s):
    out = "".join(GREEK.get(ch, ch) for ch in s)
    return re.sub(r"σ(?=$|[^\w])", "ς", out)


def crum_coptic(s):
    """Marcion's ASCII Coptic in dictionary fields: = pronominal ⸗, + qualitative †."""
    s = re.sub(r"\$\^|\^\$", "", s)
    s = s.replace("=", "⸗").replace("+", "†")
    return marcion.decode_format3(s)


def crum_meaning(s):
    s = re.sub(r"\*\^<a[^>]*>.*?</a>\^\*", "", s)
    s = re.sub(r"/\$gk: \[\[(.*?)\]\]\$/", lambda m: f'(Gk. <span class="gk">{html.escape(ascii_greek(m.group(1)))}</span>)', s)
    s = re.sub(r"\[\[(.*?)\]\]", lambda m: f'<span class="gk">{html.escape(ascii_greek(m.group(1)))}</span>', s)
    s = re.sub(r"\[(.*?)\]", lambda m: f'<span class="cop">{html.escape(crum_coptic(m.group(1)))}</span>', s)
    s = re.sub(r"\{(.*?)\}", lambda m: f"<i>{m.group(1)}</i>", s)
    s = re.sub(r"[\*\$\^]", "", s)
    return " | ".join(p.strip() for p in s.split("|") if p.strip())


def crum_forms(word):
    """'(S,B) Hwrb (S) HwrF,Horb=' -> [(['S','B'], ['ϩⲱⲣⲃ']), (['S'], ['ϩⲱⲣϥ','ϩⲟⲣⲃ⸗'])]"""
    word = re.sub(r"\*\^<a[^>]*>.*?</a>\^\*", "", word)
    out = []
    for dialects, forms in re.findall(r"\(([^)]*)\)\s*([^()]*)", word):
        fs = [crum_coptic(f.strip()) for f in forms.split(",") if f.strip()]
        out.append(([d.strip() for d in dialects.split(",")], fs))
    if not out and word.strip():
        out.append(([], [crum_coptic(f.strip()) for f in word.split(",") if f.strip()]))
    return out


def _sql_rows(text, table):
    pat = re.compile(r"insert into `" + table + r"` \(([^)]*)\) values \((.*?)\);;;\*\*\*;;;", re.S)
    for cols, vals in pat.findall(text):
        names = [c.strip("` ") for c in cols.split(",")]
        values = [marcion.unescape(v[1:-1]) if v.startswith("'") else v
                  for v in re.findall(r"'(?:[^'\\]|\\.)*'|[^,]+", vals)]
        yield dict(zip(names, values))


def _forms_html(dialects, forms):
    label = f'<span class="au">{html.escape(",".join(dialects))}</span> ' if dialects else ""
    return label + f'<span class="cop">{html.escape(", ".join(forms))}</span>'


def read_crum(path):
    """Yield (headword, [keys], html, gloss, crum_page) for each Crum word,
    with its derivations listed under it."""
    text = bz2.open(path, "rt", encoding="utf-8").read()
    derivs = {}
    for d in _sql_rows(text, "coptdrv"):
        derivs.setdefault(d.get("key_word"), []).append(d)
    for w in _sql_rows(text, "coptwrd"):
        forms = crum_forms(w.get("word", ""))
        all_forms = [f for _, fs in forms for f in fs]
        if not all_forms:
            continue
        sahidic = next((fs for ds, fs in forms if "S" in ds), all_forms)
        headword = sahidic[0]
        keys = []
        for f in sahidic + all_forms:
            k = key(f)
            if k and k not in keys:
                keys.append(k)
        meaning = crum_meaning(w.get("en", ""))
        gloss = re.sub(r"<[^>]+>", "", meaning).split(" | ")[0].strip() or None
        lines = " · ".join(_forms_html(ds, fs) for ds, fs in forms)
        parts = [f'<b class="hw cop">{html.escape(headword)}</b> <span class="bibl">Crum {html.escape(w.get("crum", ""))}</span>',
                 f'<div class="forms">{lines}</div>']
        if meaning:
            parts.append(f'<div class="sense l1">{meaning}</div>')
        for d in derivs.get(w.get("key"), []):
            dforms = crum_forms(d.get("word", "").replace("^^^", "~").replace("^^", "~"))
            dline = " · ".join(_forms_html(ds, fs) for ds, fs in dforms)
            dmean = crum_meaning(d.get("en", ""))
            if dline or dmean:
                parts.append(f'<div class="sense l2">{dline} {dmean}</div>')
            for _, fs in dforms:
                for f in fs:
                    k = key(f)
                    if k and "~" not in f and ".." not in f and k not in keys:
                        keys.append(k)
        yield headword, keys, "".join(parts), gloss, w.get("crum", "")
