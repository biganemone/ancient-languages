"""Old English helpers: lookup keys, the tokenizer, and Klaeber's Beowulf
glossary read as a lemmatisation of the poem.

Keys. Old English lemma keys carry a prefix, "ang:", because plain Latin
letters would otherwise collide with Latin lemma keys ("ac", "is", "an") in
the shared lemma and short-definition tables. Inside the prefix: lowercase,
no macrons or accents, ð written þ, no hyphens or editorial brackets, and a
homograph number where Klaeber distinguishes words (ā-cweðan 1 "kill",
ā-cweðan 2 "say").

The glossary. Klaeber lists, for nearly every word of the poem, the forms
and the lines they occur in, with their grammar ("ā-brēotan, II, destroy;
pret. 3 sg. ābrēat, 1298, ābrēot, 2930; pp. ābroten, 1599, 2707"). So each
line of the poem comes with a short list of (headword, form, grammar)
records, and the tokens of the line are matched to them: in effect a
hand-made, in-context lemmatisation and parse of Beowulf.
"""
import html
import re
import unicodedata
from collections import defaultdict

from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"
PREFIX = "ang:"

LETTERS = "A-Za-zÆæǢǣǼǽÞþÐðƿǷȝȜĀāĒēĪīŌōŪūȲȳÝýÁáÉéÍíÓóÚú"
WORD = re.compile(rf"[{LETTERS}\u0300-\u036f]+(?:[-\[\]()][{LETTERS}\u0300-\u036f\[\]()]*)*")


def strip_marks(s):
    s = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(c for c in s if not unicodedata.combining(c)))


def form_key(word):
    """For matching a written form: 'Gār-Dena' -> 'gardena', 'eorl[as]' ->
    'eorlas', 'ðā' -> 'þa'."""
    w = strip_marks(word or "").lower()
    w = re.sub(r"[-\[\]()‡†*.,;:!?'’\s]", "", w)
    return w.replace("ð", "þ").replace("ǽ", "æ").replace("ƿ", "w")


def key(headword, homograph=None):
    """The lemma key: 'ang:' + the headword's form key (+ homograph number)."""
    hw = re.sub(r"\([^)]*\)", "", headword or "")      # ǣ(e)r -> ǣr
    return PREFIX + form_key(hw) + (str(homograph) if homograph else "")


def is_old_english(k):
    return bool(k) and k.startswith(PREFIX)


def ascify(word):
    """Bosworth–Toller's lookup spelling (as madeleineth/btc_anglo_saxon
    normalises it): æ -> ae, þ/ð -> th, no marks or hyphens."""
    w = form_key(re.sub(r"\([^)]*\)", "", word))
    return w.replace("æ", "ae").replace("þ", "th").replace("œ", "oe")


def tokenize(text):
    """[(start, end, form)] for each word (character offsets). Editorial
    brackets and hyphens inside a word stay part of it: 'eorl[as]', 'Gār-Dena'."""
    out = []
    for m in WORD.finditer(text):
        s, e = m.start(), m.end()
        w = m.group()
        while w and w[-1] in "-([":                 # trailing punctuation-like marks
            w, e = w[:-1], e - 1
        while w and w[0] in "-)]":
            w, s = w[1:], s + 1
        if form_key(w):
            out.append((s, e, w))
    return out


# ------------------------------------------------------------------ grammar --
# Klaeber's word classes -> AGDT part of speech
NOUN_CLASSES = re.compile(r"^(wk\.)?(m|f|n|mc|fc|nc|mi|fi|ni|mu|fu|mja|nja|fja|mwa|nwa|fwa|ja|wa|ō|jō|wō|"
                          r"m\.n|m\.f|f\.n|n\.m|f\.m|m\.p|f\.p|n\.p|np|mp|fp|m\.\(n\)|n\.\(m\))\.?$")
VERB_CLASSES = re.compile(r"^(I|II|III|IV|V|VI|VII|w1|w2|w3|anv|prp|rd|swv|w|11|111|1V|V1|V11|Ill|lll|II1)\.?$")
CLASS_FIRST = re.compile(r"^\s*,?\s*(?:I{1,3}|IV|VI{0,2}|11|111|1V|V1|V11|Ill|lll|II1)\b\s*(?=[,;(])")
POS_WORDS = {"adj": "a", "adv": "d", "prep": "r", "conj": "c", "pron": "p", "num": "m", "interj": "i",
             "art": "l", "pers": "p", "dem": "p", "interr": "p", "rel": "p", "poss": "p", "indef": "p",
             "particle": "g", "neg": "d"}

CASE_NUMBER = re.compile(r"^([ngdaiv])([spd])([mfn]{0,3})\.?$")
TENSE = {"pres": "p", "pret": "e"}           # 'e': past (preterite); the app labels it so


def word_class(text):
    """The part of speech from the text after the headword ('m., funeral pile'
    -> 'n'; 'III, anger' -> 'v'; 'adj., …' -> 'a')."""
    for raw in re.split(r"[,;]\s*", text)[:4]:
        t = raw.strip().strip("()").strip()
        if not t:
            continue
        first = t.split()[0]
        if VERB_CLASSES.match(first) or first.startswith(("w1", "w2", "w3")):
            return "v"
        if NOUN_CLASSES.match(first) or first in ("m.", "f.", "n.") or re.match(r"^(wk\.)?[mfn]\.", first):
            return "n"
        base = first.rstrip(".").lower()
        if base in POS_WORDS:
            return POS_WORDS[base]
        if base.startswith("adj"):
            return "a"
        if base.startswith("adv"):
            return "d"
    return None


class Grammar:
    """The grammar Klaeber states before a form, kept across clauses where he
    leaves it implicit ('pret. 1 sg. efnde, 2133; 3 sg. æfnde, 1254')."""

    def __init__(self, pos):
        self.pos = pos
        self.reset()

    def reset(self):
        self.tense = self.mood = self.person = self.number = self.case = self.gender = self.degree = None
        self.participle = False

    def update(self, tok):
        t = tok.rstrip(".").lower()
        if t in TENSE:
            self.tense, self.mood, self.participle = TENSE[t], None, False
            self.case = self.gender = None
        elif t in ("opt", "subj"):
            self.mood = "o"
        elif t == "imp":
            self.mood = "m"
        elif t == "ind":
            self.mood = "i"
        elif t == "inf":
            self.mood, self.tense, self.person, self.number = "n", None, None, None
        elif t == "ger":
            self.mood, self.tense, self.person, self.number = "d", None, None, None
        elif t in ("ptc", "part"):
            self.participle, self.mood = True, "p"
            self.tense = self.tense or "p"
        elif t == "pp":
            self.participle, self.mood, self.tense = True, "p", "e"
            self.person = self.number = None
        elif t in ("1", "2", "3"):
            self.person = t
        elif t == "sg":
            self.number = "s"
        elif t == "pl":
            self.number = "p"
        elif t == "du":
            self.number = "d"
        elif t == "comp":
            self.degree = "c"
        elif t in ("sup", "superl"):
            self.degree = "s"
        elif CASE_NUMBER.match(t + "."):
            c, n, g = CASE_NUMBER.match(t + ".").groups()
            self.case, self.number, self.gender = c, n, (g[:1] if g else None)
            self.person = None
        else:
            return False
        return True

    def tag(self, bare=False):
        """AGDT-style 9-character tag. bare: the form is the headword itself
        (Klaeber leaves nom. sg. and the infinitive unmarked)."""
        pos = self.pos or "-"
        if bare and not any((self.tense, self.mood, self.case, self.person)):
            if pos == "v":
                return "v---n----"
            if pos == "n":
                return "n-s----n-"
            return pos + "--------" if pos != "-" else None
        if pos == "-" and (self.tense or self.person or self.mood):
            pos = "v"
        verbal = pos == "v"
        if verbal and self.participle:
            pos = "t"
        mood = self.mood
        if pos == "v" and not mood and (self.person or self.tense):
            mood = "i"
        if not verbal:                      # left over from a verb form cited before
            mood = None
        person = self.person if pos == "v" else None
        tense = self.tense if verbal else None
        degree = self.degree if pos in ("a", "d") else None
        tag = (pos + (person or "-") + (self.number or "-") + (tense or "-") + (mood or "-")
               + "-" + (self.gender or "-") + (self.case or "-") + (degree or "-"))
        return tag if tag[1:] != "-" * 8 or pos != "-" else None


ABBREVIATIONS = {"pres", "pret", "opt", "subj", "imp", "ind", "inf", "ger", "ptc", "part", "pp", "sg", "pl",
                 "du", "comp", "sup", "superl", "1", "2", "3"}
SKIP_AFTER = {"w", "cp", "cf", "see", "si", "n", "q", "lang", "note", "notes", "ib", "ff", "f", "l", "p", "pp",
              "intr", "trans", "absol", "subst", "wk", "st", "uninfl", "expressed", "used", "freq", "occas",
              "acc", "dat", "gen", "instr", "nom"}


def is_label(el):
    """A grammar label the transcription marked as a gloss ('gs', 'b')."""
    t = "".join(el.itertext()).strip().rstrip(";:,")
    return bool(CASE_NUMBER.match(t if t.endswith(".") else t + ".")) or t.rstrip(".") in ABBREVIATIONS \
        or len(t) <= 1


def entry_body(el):
    """The entry's text without its glosses (English) and titles, keeping
    line numbers; parenthesised and bracketed asides are marked so the
    parser can skip them."""
    parts = []

    def rec(e, skip=False):
        name = e.tag.split("}")[-1] if isinstance(e.tag, str) else ""
        drop = skip or (name == "seg" and e.get("type") == "translation" and not is_label(e)) \
            or name in ("title", "bibl")
        if e.text and not drop and name != "entryFree":
            parts.append(e.text)
        elif e.text and name == "entryFree":
            parts.append(e.text)
        for c in e:
            rec(c, drop)
            if c.tail:
                parts.append(c.tail if not skip else "")
    rec(el)
    return "".join(parts)


def clean_gloss(t):
    """Klaeber capitalises the Modern English cognate ('EVENing-LIGHT',
    'WHO, WHAT'): lowercase it for a short definition; drop stray brackets."""
    t = re.sub(r"\b([A-Z]) (?=[A-Z]\b)", r"\1", t)            # OCR's spaced capitals: "H E"
    t = re.sub(r"[A-ZÆ]{2,}[a-z]*", lambda m: m.group().lower(), t)
    t = t.strip(" :;,")
    if t.count("(") != t.count(")"):
        t = t.replace("(", "").replace(")", "")
    return t.strip(" :;,")


def glosses(el):
    """The entry's English glosses, without the titles of works cited (which
    the transcription also marks as glosses: 'R.-L.', 'Oldest Engl. Texts')."""
    out = []
    for g in el.iter(TEI + "gloss"):
        t = " ".join("".join(g.itertext()).split())
        if not t or len(t.strip(" ;:,.()")) <= 1 or is_label(g) or re.search(r"\b(und|der|die|das)\b", t) \
                or re.match(r"^[A-Z][a-z]+\.$", t):
            continue
        if out and (re.search(r"[A-Za-z]\.(\s|$|-)", t) or re.match(r"^[A-Z][a-z]+\.?$", t)):
            continue
        t = clean_gloss(t)
        if t and t not in out:
            out.append(t)
    return out


def entry_html(el):
    """The entry as simple HTML for the lexicon view."""
    def rec(e):
        name = e.tag.split("}")[-1] if isinstance(e.tag, str) else ""
        inner = (e.text or "") + "".join(rec(c) + (c.tail or "") for c in e)
        inner = inner.replace("&", "&amp;").replace("<", "&lt;") if False else inner
        if name == "orth":
            return f"<b>{inner}</b>"
        if name == "gloss":
            return f"<i>{inner}</i>"
        if name == "title":
            return f"<cite>{inner}</cite>"
        if name == "hi" and e.get("rend") == "super":
            return f"<sup>{inner}</sup>"
        if name == "hi":
            return f"<i>{inner}</i>"
        return inner
    import html
    def esc(e):
        for x in e.iter():
            if x.text:
                x.text = html.escape(x.text, quote=False)
            if x.tail:
                x.tail = html.escape(x.tail, quote=False)
    esc(el)
    return " ".join(rec(el).split())


class Glossary:
    """Klaeber's glossary: entries, and per line of Beowulf the forms cited there."""

    def __init__(self, path, poem_words=None):
        """poem_words: the form keys of every word of the poem; a word in an
        entry counts as a cited form only if the poem has it (Klaeber's English
        and his context words, "(mid) ~", are not forms)."""
        self.poem_words = poem_words
        self.keys = set()
        root = etree.parse(path).getroot()
        self.entries = []               # dict(id, headword, key, pos, gloss, html, proper)
        self.by_line = defaultdict(list)    # line -> [(entry index, form or None, tag)]
        self.forms = defaultdict(list)      # form key -> [(entry index, tag)]
        section = None
        homographs = defaultdict(int)
        for div in root.iter(TEI + "div"):
            if div.get("subtype") != "card":
                continue
            head = div.find(TEI + "head")
            label = "".join(head.itertext()).strip() if head is not None else ""
            if "FINNSBURG" in label.upper():
                section = "finnsburg"
            elif "PROPER NAMES" in label.upper() and section != "finnsburg":
                section = "names"
            elif section is None:
                section = "main"
            if section == "finnsburg":
                continue
            for el in div.iter(TEI + "entryFree"):
                self._add(el, section == "names", homographs)

    def _add(self, el, proper, homographs):
        orths = ["".join(o.itertext()).strip().rstrip(",;") for o in el.findall(TEI + "orth")]
        if not orths:
            return
        headword = orths[0].split(",")[0].strip()
        n = el.get("n") or ""
        hom = re.search(r"(\d+)$", n)
        hom = int(hom.group(1)) if hom else None
        body = entry_body(el)
        first = el.find(TEI + "orth")
        # text after the headword(s), before the first gloss: the word class
        after = body.split(orths[0], 1)[-1] if orths[0] in body else body
        pos = "n" if proper else word_class(after)
        g = glosses(el)
        ref = el.find(f".//{TEI}ref")
        is_ref = bool(re.match(r"^\s*,?\s*see\b", after)) and not re.search(r"\d", after.split("see", 1)[-1][:40])
        idx = len(self.entries)
        k = key(headword, hom)
        if k in self.keys:                     # in (prep.) and in(n) (noun): keep the bracketed letters
            k = PREFIX + form_key(headword) + (str(hom) if hom else "")
        while k in self.keys:
            k += "+"
        self.keys.add(k)
        self.entries.append(dict(headword=headword, key=k, pos=pos,
                                 gloss="; ".join(g[:3]).rstrip(":;,") if g else None,
                                 html=entry_html(el), proper=proper, ref=is_ref,
                                 also=[o for o in orths[1:]],
                                 see="".join(ref.itertext()).strip() if ref is not None else None))
        self._citations(idx, headword, orths, after, pos)

    def _citations(self, idx, headword, orths, text, pos):
        text = re.sub(r"--\s*Cpds?\.:.*$", "", text, flags=re.S)    # compounds listed at the end
        text = CLASS_FIRST.sub("", text)                                # a verb class (III, OCR "111")
        grammar = Grammar(pos)
        form = None
        last_form = None
        depth_paren = depth_bracket = 0
        skip_next = False
        f_ref = False
        bracket_line = None
        for m in re.finditer(r"\d+|[^\s,;:()\[\]]+|[()\[\];,:]", text):
            tok = m.group()
            if tok == "(":
                depth_paren += 1
                continue
            if tok == ")":
                depth_paren = max(0, depth_paren - 1)
                continue
            if tok == "[":
                depth_bracket += 1
                rest = text[m.end():m.end() + 8]
                bracket_line = re.match(r"\s*(\d+)\s*\]", rest)
                continue
            if tok == "]":
                depth_bracket = max(0, depth_bracket - 1)
                continue
            if tok == ";":
                form = None
                skip_next = False
                continue
            if tok in (",", ":"):
                skip_next = False
                continue
            if depth_paren:
                continue
            if depth_bracket and not re.match(r"\d+$", tok):
                if tok.rstrip(".") == "F":
                    f_ref = True
                continue
            if tok in ("1", "2", "3") and re.match(r"\s*(sg|pl|du|dual|pers)\b", text[m.end():m.end() + 8]):
                grammar.update(tok)                           # person ("3 sg."), not a line
                form = None
                continue
            if tok.isdigit():
                if skip_next or f_ref:
                    if f_ref and depth_bracket == 0:
                        f_ref = False
                    continue
                if depth_bracket and not bracket_line:
                    continue
                line = int(tok)
                if re.match(r"\s*(times|time|x\b|\.\s*times)", text[m.end():m.end() + 8]):
                    continue                                  # a count ("181 times"), not a line
                if 1 <= line <= 3182:
                    if form == "~":
                        self.by_line[line].append((idx, headword, grammar.tag()))
                        if last_form:
                            self.by_line[line].append((idx, last_form, grammar.tag()))
                        continue
                    self.by_line[line].append((idx, form, grammar.tag(bare=form is None)))
                    if form and not form.startswith("-"):
                        self.forms[form_key(form)].append((idx, grammar.tag()))
                continue
            f_ref = False
            low = tok.rstrip(".").lower()
            if skip_next:
                skip_next = False
                continue
            if grammar.update(tok):
                if low in ("pres", "pret", "inf", "ger", "pp") or CASE_NUMBER.match(low + "."):
                    form = None
                continue
            if low in SKIP_AFTER and tok.endswith("."):
                if low in ("w", "cp", "cf", "see"):
                    skip_next = True
                continue
            if tok == "~":            # the headword (or, after a grammar label, the last form)
                form = "~"
                continue
            if tok.startswith("-") and len(tok) > 1:
                form = tok
                continue
            if re.match(rf"^[{LETTERS}\u0300-\u036f\-]+$", tok) and not tok.endswith(".") \
                    and (self.poem_words is None or form_key(tok) in self.poem_words):
                form = tok
                last_form = tok
                continue


def suffix_match(token_key, suffix, headword):
    s = form_key(suffix)
    h = form_key(headword)
    return bool(s) and token_key.endswith(s) and token_key[:2] == h[:2] and len(token_key) > len(s)


def similarity(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_line(tokens, records, glossary):
    """tokens: [form]; records: [(entry index, form or None, tag)] cited at
    this line. -> [(entry index, tag, score) or None] per token.

    A token takes the record whose form it is (ties: the entry whose headword
    is most like the token, since a record's "form" can be a context word:
    "on him byrne scān, 405" under on); then a suffix ("ds. -e"); then the
    headword itself (Klaeber leaves nom. sg. and the infinitive unmarked)."""
    out = []
    for tok in tokens:
        tk = form_key(tok)
        best = None
        for idx, form, tag in records:
            e = glossary.entries[idx]
            hk = form_key(re.sub(r"\([^)]*\)", "", e["headword"]))
            like = similarity(tk, hk)
            score = 0
            if form and not form.startswith("-"):
                if tk in (form_key(form), form_key(re.sub(r"\([^)]*\)", "", form))):
                    # a context word cited under another entry ("Bēowulf maðelode, 405"
                    # under Bēowulf): only pronouns and verbs have forms unlike
                    # their headword (mē: ic; wæs: wesan)
                    score = 3 + like if like >= 0.4 or e["pos"] in ("p", "v", None) else 1.2 + like
            elif form:
                if suffix_match(tk, form, e["headword"]):
                    score = 2.5 + like
            if not score:
                if tk == hk or tk in {form_key(a) for a in e["also"]}:
                    score = 2.8 + (0 if form else 0.5)
                elif like >= 0.75 and (not form or form_key(form) == hk):
                    score = 1 + like
            if score and (best is None or score > best[2]):
                best = (idx, tag if score >= 2.5 else None, score)
        out.append(best)
    return out


class Fallback:
    """For words Klaeber cites only by count ("ond, conj., 311 times") or
    under a cross-reference: the entry the form or headword points to, the
    most often cited if several."""

    def __init__(self, glossary):
        self.g = glossary
        self.cited = defaultdict(int)
        self.index = defaultdict(lambda: defaultdict(int))
        self.tags = defaultdict(lambda: defaultdict(set))
        by_key = defaultdict(list)
        for i, e in enumerate(glossary.entries):
            by_key[form_key(re.sub(r"\([^)]*\)", "", e["headword"]))].append(i)
        for line, recs in glossary.by_line.items():
            for i, form, tag in recs:
                self.cited[i] += 1
                e = glossary.entries[i]
                if form and not form.startswith("-") and (
                        e["pos"] in ("p", "v", None) or similarity(form_key(form), form_key(e["headword"])) >= 0.4):
                    self.index[form_key(form)][i] += 1
                    self.tags[form_key(form)][i].add(tag)
        for k, ids in by_key.items():
            for i in ids:
                target = self.follow(i, by_key)
                if target is not None:
                    self.index[k][target] += 1000      # the headword itself
                    for a in glossary.entries[i]["also"]:
                        self.index[form_key(a)][target] += 1000

    def follow(self, i, by_key, depth=0):
        e = self.g.entries[i]
        if not e["ref"]:
            return i
        if depth > 2 or not e["see"]:
            return None
        k = form_key(re.sub(r"\([^)]*\)", "", e["see"]))
        if k not in by_key:
            near = [kk for kk in by_key if similarity(k, kk) >= 0.85]
            if not near:
                return None
            k = max(near, key=lambda kk: similarity(k, kk))
        return self.follow(by_key[k][0], by_key, depth + 1)

    # common forms whose entries cite them only by count, or which a context
    # word in another entry would otherwise claim
    OVERRIDES = {"wæs": "eom", "wæron": "eom", "wære": "eom", "wæran": "eom", "næs": "eom", "wes": "eom",
                 "hine": "he", "hyne": "he", "hio": "he", "heo": "he", "hit": "he", "hyt": "he",
                 "mine": "min", "minne": "min", "minum": "min", "minra": "min", "mines": "min",
                 "wit": "ic", "unc": "ic", "git": "þu", "inc": "þu", "sio": "se", "seo": "se",
                 "hwæt": "ang:hwæt2"}     # (line 1: Klaeber cites it as "I.")

    def headword_index(self, k):
        for i, e in enumerate(self.g.entries):
            if form_key(re.sub(r"\([^)]*\)", "", e["headword"])) == k and not e["ref"]:
                return i
        return None

    def guess(self, token):
        tk = form_key(token)
        if tk in self.OVERRIDES:
            target = self.OVERRIDES[tk]
            i = (next((j for j, e in enumerate(self.g.entries) if e["key"] == target), None)
                 if target.startswith(PREFIX) else self.headword_index(target))
            if i is not None:
                return (i, None, 0.5)
        cands = self.index.get(tk)
        if not cands:
            # an inflected name or compound: the nearest headword with the same beginning
            near = [(similarity(tk, k), k) for k in self.index if k[:3] == tk[:3] and len(k) > 3]
            near = [x for x in near if x[0] >= 0.8]
            if not near:
                return None
            cands = self.index[max(near)[1]]
        i = max(cands, key=lambda j: (cands[j], self.cited[j]))
        tags = self.tags.get(tk, {}).get(i, set()) - {None}
        tag = next(iter(tags)) if len(tags) == 1 else None
        return (i, tag, 0.5)


def display_headword(hw):
    """'sē (se)' -> 'sē'; 'Hrēðel (Hrǣdel' -> 'Hrēðel'; 'heal(l)' stays."""
    hw = re.sub(r"\s+\(.*$", "", hw).strip()
    return hw.rstrip(",;:")


def lemmatise(lines, glossary, fallback=None):
    """lines: {n: [token form]} -> {n: [(entry index, tag, how) or None]}.
    how: 'line' (Klaeber cites this word at this line) or 'form' (by its form)."""
    fallback = fallback or Fallback(glossary)
    out = {}
    for n, toks in lines.items():
        res = []
        for tok, r in zip(toks, match_line(toks, glossary.by_line.get(n, []), glossary)):
            if r is None or r[2] < 2:
                f = fallback.guess(tok)
                if f is not None and (r is None or f[0] != r[0]):
                    r = f
            if r is None:
                res.append(None)
                continue
            i, tag, score = r
            pos = glossary.entries[i]["pos"]
            if not tag and pos:
                tag = pos + "-" * 8
            res.append((i, tag, "line" if score >= 2 else "form"))
        out[n] = res
    return out


# ------------------------------------------------- Bosworth–Toller glosses --
GRAM = re.compile(r"^(neut|masc|fem|impert|irreg|m|f|n|adj|adv|v|pl|gen|dat|acc|nom|prep|conj|pron|interj|indecl|pp|p|sing|comp|sup|part|"
                  r"pres|impers|intrans|trans|refl|num|def|indef|v\. intrans|v\. trans|and|or|e\.g|i\.e|q\.v|cf|dat\.|"
                  r"gen\.|acc\.|w\.|with|also|v\. a|v\. n|in|of|the|a|v\. r)[\s.,;:]*$", re.I)
def bt_gloss(defn):
    """The first definition in a Bosworth–Toller entry: its first italic phrase
    that is not grammar ('m.', 'adj.', 'v. trans.')."""
    body = re.sub(r"^\s*<B>.*?</B>", "", defn, count=1, flags=re.S)
    body = re.sub(r"\[[^\]]*\]", "", body)                 # etymology: [cyn people, -ing …]
    for m in re.finditer(r"<I>(.*?)</I>", body, re.S):
        t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        t = " ".join(t.split()).strip(" ,;:.")
        t = re.sub(r"^((m|f|n|adj|adv|pl|gen|dat|acc|nom|prep|conj|pron|indecl|v\. (in)?trans|v)\.\s*)+", "", t, flags=re.I).strip(" ,;:.")
        if len(t) < 2 or GRAM.match(t) or not re.search(r"[a-z]{3}", t):
            continue
        t = re.sub(r"^(To|A|An|The) ", lambda x: x.group(1).lower() + " ", t)
        if len(t) > 90:
            cut = t[:90].rsplit(",", 1)[0]
            t = cut if len(cut) > 20 else t[:90].rsplit(" ", 1)[0] + "…"
        return t
    return None
