"""Old Norse lemmas and parses, automatic: forms generated from the headwords
of Zoëga's Concise Dictionary of Old Icelandic (1910; the JSON of
stscoundrel/old-icelandic-zoega, MIT), and ranked by lemma frequency over the
corpus (a few rounds of EM, as oe_forms.py does for Old English).

Zoëga gives each headword's word class and, in brackets, what is needed to
inflect it: a noun's genitive and plural endings ("hestr (-s, -ar), m.") or
irregular forms ("jörð (gen. jarðar, dat. jörðu; pl. jarðir), f."), a strong
verb's principal parts ("taka (tek; tók, tókum; tekinn), v."), a weak verb's
class ("kalla (að), v."). From these, regular paradigms: nouns (strong and
weak, with the suffixed article), adjectives (strong and weak), verbs
(present and past indicative, infinitive, imperative, participles; active
and middle). Pronouns, the article and the commonest irregular verbs are
listed by hand (CLOSED). Comparison, the subjunctive and most sound changes
other than u-umlaut are left out, so some forms get no reading and some get a
wrong one; every reading is offered, most likely first.

Tags are AGDT's nine positions (pos, person, number, tense, mood, voice,
gender, case, degree), as for Greek, so the app's parse formatting reads them.
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict

import oldnorse as on

PARSE_WORDS = [
    {"n": "noun", "v": "verb", "t": "participle", "a": "adjective", "d": "adverb", "l": "article",
     "c": "conjunction", "r": "preposition", "p": "pronoun", "m": "numeral", "i": "interjection"},
    {"1": "1st person", "2": "2nd person", "3": "3rd person"},
    {"s": "singular", "p": "plural", "d": "dual"},
    {"p": "present", "e": "past"},
    {"i": "indicative", "s": "subjunctive", "n": "infinitive", "m": "imperative", "p": "participle"},
    {"m": "middle"},
    {"m": "masculine", "f": "feminine", "n": "neuter"},
    {"n": "nominative", "g": "genitive", "d": "dative", "a": "accusative"},
    {"c": "comparative", "s": "superlative"},
]
CASES = "nadg"


def tag(pos, person="-", number="-", tense="-", mood="-", voice="-", gender="-", case="-", degree="-"):
    return pos + person + number + tense + mood + voice + gender + case + degree


def describe(t):
    """'noun · singular · masculine · dative'."""
    if not t or len(t) < 9:
        return ""
    out = []
    for i, ch in enumerate(t[:9]):
        w = PARSE_WORDS[i].get(ch)
        if w and not (t[0] == "t" and i == 4):
            out.append(w)
    return " · ".join(out)


def clean(s):
    return re.sub(r"<[^>]+>", "", s).replace("’", "'").strip()


def u_umlaut(stem):
    """a in the last syllable becomes ö before an ending in u (land, löndum)."""
    m = re.search(r"a(?=[^aeiouyáéíóúýæöø]*$)", stem)
    return stem[:m.start()] + "ö" + stem[m.end():] if m else stem


def add(stem, ending):
    if ending.startswith("u"):
        stem = u_umlaut(stem)
    return stem + ending


# ------------------------------------------------------------------- nouns --
ARTICLE = {  # (gender, number, case) -> ending added to the inflected form
    ("m", "s", "n"): "inn", ("m", "s", "a"): "inn", ("m", "s", "d"): "inum", ("m", "s", "g"): "ins",
    ("f", "s", "n"): "in", ("f", "s", "a"): "ina", ("f", "s", "d"): "inni", ("f", "s", "g"): "innar",
    ("n", "s", "n"): "it", ("n", "s", "a"): "it", ("n", "s", "d"): "inu", ("n", "s", "g"): "ins",
    ("m", "p", "n"): "inir", ("m", "p", "a"): "ina", ("m", "p", "d"): "inum", ("m", "p", "g"): "inna",
    ("f", "p", "n"): "inar", ("f", "p", "a"): "inar", ("f", "p", "d"): "inum", ("f", "p", "g"): "inna",
    ("n", "p", "n"): "in", ("n", "p", "a"): "in", ("n", "p", "d"): "inum", ("n", "p", "g"): "inna",
}


def with_article(form, g, n, c):
    art = ARTICLE[(g, n, c)]
    if form.endswith("um") and art.startswith("i"):          # löndum + inum -> löndunum
        return form[:-1] + art[1:]
    if form and form[-1] in "aeiouáéíóú" and art.startswith("i"):   # saga + in -> sagan
        return form + art[1:]
    return form + art


def noun_forms(hw, gender, info):
    """[(form, tag)] for a noun."""
    out = {}
    g = gender
    gen_end, pl_end = None, None
    m = re.match(r"\(\s*-(\w+)\s*,\s*-(\w+)\s*\)", info)
    if m:
        gen_end, pl_end = m.group(1), m.group(2)
    weak = (g == "m" and hw.endswith("i")) or (g in "fn" and hw.endswith("a"))
    if weak:
        stem = hw[:-1]
        if g == "m":
            sg = {"n": hw, "a": stem + "a", "d": stem + "a", "g": stem + "a"}
            pl = {"n": stem + "ar", "a": stem + "a", "d": add(stem, "um"), "g": stem + "a"}
        elif g == "f":
            sg = {"n": hw, "a": add(stem, "u"), "d": add(stem, "u"), "g": add(stem, "u")}
            pl = {"n": add(stem, "ur"), "a": add(stem, "ur"), "d": add(stem, "um"), "g": stem + "na"}
        else:
            sg = {c: hw for c in CASES}
            pl = {"n": add(stem, "u"), "a": add(stem, "u"), "d": add(stem, "um"), "g": stem + "na"}
    else:
        if g == "m":
            if re.search(r"[^aeiouyáéíóúýæöø]r$", hw):
                stem = hw[:-1]
            elif re.search(r"[áéíóúýæœæ](ll|nn)$|[aeiouy]nn$", hw) and not hw.endswith("ss"):
                stem = hw[:-1]
            else:
                stem = hw[:-1] if hw.endswith("r") else hw
            gs = stem + (gen_end or "s")
            sg = {"n": hw, "a": stem, "d": stem + "i", "g": gs}
            plural = pl_end or "ar"
            if plural == "ir":
                pl = {"n": stem + "ir", "a": stem + "i", "d": add(stem, "um"), "g": stem + "a"}
            else:
                pl = {"n": stem + "ar", "a": stem + "a", "d": add(stem, "um"), "g": stem + "a"}
        elif g == "f":
            stem = hw
            sg = {"n": hw, "a": hw, "d": hw, "g": stem + (gen_end or "ar")}
            plural = pl_end or "ar"
            pl = {"n": stem + plural, "a": stem + plural, "d": add(stem, "um"), "g": stem + "a"}
        else:
            stem = hw
            sg = {"n": hw, "a": hw, "d": stem + "i", "g": stem + (gen_end or "s")}
            pl = {"n": u_umlaut(stem), "a": u_umlaut(stem), "d": add(stem, "um"), "g": stem + "a"}
    for num, forms in (("s", sg), ("p", pl)):
        for c, f in forms.items():
            t = tag("n", number=num, gender=g, case=c)
            out.setdefault(f, set()).add(t)
            out.setdefault(with_article(f, g, num, c), set()).add(t)
    # irregular forms Zoëga writes out: (gen. jarðar, dat. jörðu; pl. jarðir)
    for label, case, num in (("gen.", "g", "s"), ("dat.", "d", "s"), ("acc.", "a", "s"), ("pl.", "n", "p"),
                             ("gen. pl.", "g", "p"), ("dat. pl.", "d", "p")):
        for m in re.finditer(re.escape(label) + r"\s+([^\s,;()]+)", info):
            f = m.group(1)
            if f.startswith("-") or not re.match(rf"^[{on.LETTERS}]+$", f):
                continue
            t = tag("n", number=num, gender=g, case=case)
            out.setdefault(f, set()).add(t)
            out.setdefault(with_article(f, g, num, case), set()).add(t)
    return [(f, t) for f, ts in out.items() for t in ts]


# -------------------------------------------------------------- adjectives --
def adjective_forms(hw, info):
    out = []
    if hw.endswith("r") and len(hw) > 2 and hw[-2] not in "aeiouyáéíóúýæöø":
        stem = hw[:-1]
    elif re.search(r"[áéíóúýæœ](ll|nn)$", hw):
        stem = hw[:-1]
    else:
        stem = hw
    strong = {
        ("m", "s"): {"n": hw, "a": stem + "an", "d": add(stem, "um"), "g": stem + "s"},
        ("f", "s"): {"n": u_umlaut(stem), "a": stem + "a", "d": stem + "ri", "g": stem + "rar"},
        ("n", "s"): {"n": stem + "t", "a": stem + "t", "d": add(stem, "u"), "g": stem + "s"},
        ("m", "p"): {"n": stem + "ir", "a": stem + "a", "d": add(stem, "um"), "g": stem + "ra"},
        ("f", "p"): {"n": stem + "ar", "a": stem + "ar", "d": add(stem, "um"), "g": stem + "ra"},
        ("n", "p"): {"n": u_umlaut(stem), "a": u_umlaut(stem), "d": add(stem, "um"), "g": stem + "ra"},
    }
    weak = {
        ("m", "s"): {"n": stem + "i", "a": stem + "a", "d": stem + "a", "g": stem + "a"},
        ("f", "s"): {"n": stem + "a", "a": add(stem, "u"), "d": add(stem, "u"), "g": add(stem, "u")},
        ("n", "s"): {"n": stem + "a", "a": stem + "a", "d": stem + "a", "g": stem + "a"},
    }
    for (g, n), forms in list(strong.items()) + list(weak.items()):
        for c, f in forms.items():
            out.append((f, tag("a", number=n, gender=g, case=c)))
    for g in "mfn":
        for c in CASES:
            out.append((add(stem, "u") if c != "d" else add(stem, "um"), tag("a", number="p", gender=g, case=c)))
    m = re.match(r"\(([^,)]+),\s*([^,)]+)\)", info)        # (góð, gott): the feminine and neuter
    if m:
        out.append((m.group(1).strip(), tag("a", number="s", gender="f", case="n")))
        out.append((m.group(2).strip(), tag("a", number="s", gender="n", case="n")))
        out.append((m.group(2).strip(), tag("a", number="s", gender="n", case="a")))
    return out


# ------------------------------------------------------------------- verbs --
def participle_forms(pp, tense):
    """A participle declined as an adjective (tagged t, with its tense)."""
    out = []
    for f, t in adjective_forms(pp, ""):
        out.append((f, "t" + t[1:3] + tense + "p" + t[5:]))
    if pp.endswith("inn"):                                   # tekinn, tekit, teknir, tekna
        st = pp[:-3]
        for f, g, n, c in ((st + "it", "n", "s", "n"), (st + "it", "n", "s", "a"), (st + "nir", "m", "p", "n"),
                           (st + "na", "m", "p", "a"), (st + "na", "m", "s", "a"), (st + "nar", "f", "p", "n"),
                           (st + "num", "m", "s", "d"), (st + "ins", "m", "s", "g"), (st + "in", "f", "s", "n")):
            out.append((f, tag("t", number=n, tense=tense, mood="p", gender=g, case=c)))
    return out


def middle(f):
    """The middle voice of a form, in the editions' spellings: kalla -> kallask,
    kallaz; kvað -> kvazk, kvaz; kallaði -> kallaðisk, kallaðiz."""
    if f.endswith("r") and len(f) > 2:
        f = f[:-1]
    if f[-1:] in "ðdt":
        base = f[:-1]
        return [base + "zk", base + "z", f + "sk"]
    return [f + "sk", f + "z", f + "zk", f + "st"]


def verb_forms(hw, info):
    out = []
    stem = hw[:-1] if hw.endswith("a") else hw
    finite = []                    # (form, person, number, tense, mood)
    pres_pl = [(add(stem, "um"), "1", "p"), (stem + "ið", "2", "p"), (hw, "3", "p")]
    finite += [(f, p, n, "p", "i") for f, p, n in pres_pl]
    if re.match(r"\(\s*að\s*\)", info):                        # kalla (að): kallaði
        finite += [(stem + "a", "1", "s", "p", "i"), (stem + "ar", "2", "s", "p", "i"), (stem + "ar", "3", "s", "p", "i")]
        past = stem + "að"
        finite += [(past + "a", "1", "s", "e", "i"), (past + "i", "1", "s", "e", "i"), (past + "ir", "2", "s", "e", "i"),
                   (past + "i", "3", "s", "e", "i"), (u_umlaut(stem) + "uðum", "1", "p", "e", "i"),
                   (u_umlaut(stem) + "uðuð", "2", "p", "e", "i"), (u_umlaut(stem) + "uðu", "3", "p", "e", "i")]
        out += participle_forms(stem + "aðr", "e") + [(stem + "at", tag("t", number="s", tense="e", mood="p", gender="n", case="n"))]
        finite += [(stem + "a", "2", "s", "p", "m")]
    else:
        parts = re.match(r"\(([^;)]+);\s*([^,;)]+)(?:\s*(?:or [^,;)]+)?),\s*([^;)]+?)(?:\s+or [^;)]+)?;\s*([^)]+)\)", info)
        if parts:                                              # taka (tek; tók, tókum; tekinn)
            pres1, past1, pastpl, pp = (p.strip().split(" or ")[0].strip() for p in parts.groups())
            weak_past = pres1.endswith("i") or past1.endswith("a")          # hafa (hefi; hafða, höfðum; hafðr)
            if weak_past:
                finite += [(pres1, "1", "s", "p", "i"), (pres1[:-1] + "r", "2", "s", "p", "i"),
                           (pres1[:-1] + "r", "3", "s", "p", "i")]
                pst = past1[:-1]
                finite += [(past1, "1", "s", "e", "i"), (pst + "i", "1", "s", "e", "i"), (pst + "ir", "2", "s", "e", "i"),
                           (pst + "i", "3", "s", "e", "i")]
            else:
                p3 = pres1 + "r"                     # fer -> ferr, tek -> tekr (and as written: vex, kemr)
                finite += [(pres1, "1", "s", "p", "i"), (p3, "2", "s", "p", "i"), (p3, "3", "s", "p", "i"),
                           (pres1, "3", "s", "p", "i")]
                finite += [(past1, "1", "s", "e", "i"), (past1 + "t", "2", "s", "e", "i"), (past1, "3", "s", "e", "i")]
            if pastpl.endswith("um"):
                ps = pastpl[:-2]
                finite += [(pastpl, "1", "p", "e", "i"), (ps + "uð", "2", "p", "e", "i"), (ps + "u", "3", "p", "e", "i")]
            finite += [(pres1 if not pres1.endswith("i") else stem, "2", "s", "p", "m")]
            out += participle_forms(pp, "e")
        elif re.match(r"\(\s*[^;,)]+,\s*[^;,)]+a\s*,\s*[^;,)]+\)", info):     # spyrja (spyr, spurða, spurðr)
            pres1, past1, pp = (x.strip() for x in info.strip("()").split(","))
            finite += [(pres1, "1", "s", "p", "i"), (pres1 + "r", "3", "s", "p", "i"), (pres1, "3", "s", "p", "i")]
            pst = past1[:-1]
            finite += [(past1, "1", "s", "e", "i"), (pst + "i", "1", "s", "e", "i"), (pst + "ir", "2", "s", "e", "i"),
                       (pst + "i", "3", "s", "e", "i"), (u_umlaut(pst) + "um", "1", "p", "e", "i"),
                       (u_umlaut(pst) + "u", "3", "p", "e", "i")]
            out += participle_forms(pp, "e")
        else:                                                   # (ð), (d), (t), (-ta, -tr), or nothing: weak
            m = re.match(r"\(\s*-?(ð|d|t)(?:a|i)?\b", info)
            dent = m.group(1) if m else "ð"
            mm = re.match(r"\(\s*[^;)]*;\s*([^,;)]+?a)\b", info)     # spyrja (spyr; spurða; spurðr)
            if mm and not mm.group(1).startswith("-"):
                alt = mm.group(1)[:-1]
                finite += [(alt + "i", "3", "s", "e", "i"), (alt + "a", "1", "s", "e", "i"),
                           (u_umlaut(alt) + "u", "3", "p", "e", "i"), (u_umlaut(alt) + "um", "1", "p", "e", "i")]
                out += participle_forms(alt + "r", "e")
            finite += [(stem, "1", "s", "p", "i"), (stem + "ir", "2", "s", "p", "i"), (stem + "ir", "3", "s", "p", "i"),
                       (stem + "r", "3", "s", "p", "i")]
            past = stem + dent
            finite += [(past + "a", "1", "s", "e", "i"), (past + "i", "1", "s", "e", "i"), (past + "ir", "2", "s", "e", "i"),
                       (past + "i", "3", "s", "e", "i"), (u_umlaut(past) + "um", "1", "p", "e", "i"),
                       (u_umlaut(past) + "uð", "2", "p", "e", "i"), (u_umlaut(past) + "u", "3", "p", "e", "i")]
            out += participle_forms(past + "r", "e")
            finite += [(stem, "2", "s", "p", "m")]
    out.append((hw, tag("v", tense="p", mood="n")))
    out += [(m, tag("v", tense="p", mood="n", voice="m")) for m in middle(hw)]
    out += participle_forms(stem + "andi", "p")[:1]
    out.append((stem + "andi", tag("t", tense="p", mood="p")))
    for f, p, n, te, mo in finite:
        out.append((f, tag("v", person=p, number=n, tense=te, mood=mo)))
        out += [(m, tag("v", person=p, number=n, tense=te, mood=mo, voice="m")) for m in middle(f)]
    return out


# ------------------------------------------------------------ closed class --
def _pron(lemma, pos, rows):
    """rows: 'form:number gender case …' (gender may be '-')."""
    out = []
    for item in rows.split():
        form, spec = item.split(":")
        for s in spec.split("/"):
            n, g, c = s
            out.append((form, lemma, tag(pos, number=n, gender=g, case=c)))
    return out


def _poss(lemma):
    """minn, þinn, sinn: mín, mínum, mitt, …"""
    s, short = lemma[:-3] + "ín", lemma[:-3] + "i"           # sinn: sín-, si-
    return _pron(lemma, "p", f"{lemma}:smn/sma {s}um:smd/pmd/pfd/pnd {s}s:smg/sng {s}:sfn/pnn/pna "
                             f"{s}a:sfa/pma {short}nni:sfd {short}nnar:sfg {short}tt:snn/sna {short}t:snn/sna "
                             f"{s}u:snd {s}ir:pmn {s}ar:pfn/pfa {short}nna:pmg/pfg/png")


# particles and conjunctions Zoëga's entries do not label in a way read here
PARTICLES = {"at": ["c", "r", "g"], "sem": ["c"], "es": ["c"], "er": ["c"], "eptir": ["r", "d"], "eftir": ["r", "d"],
             "þvíat": ["c"], "fyr": ["r"], "fyrir": ["r"], "framm": ["d"], "fram": ["d"], "hvárt": ["c"],
             "ok": ["c"], "en": ["c"], "eða": ["c"], "né": ["c"], "þá": ["d"], "nú": ["d"], "svá": ["d"],
             "eigi": ["d"], "ekki": ["d"], "um": ["r"], "of": ["r"], "við": ["r"], "með": ["r"], "frá": ["r"],
             "ór": ["r"], "úr": ["r"], "í": ["r"], "á": ["r"], "af": ["r"], "til": ["r"], "undir": ["r"],
             "yfir": ["r"], "þar": ["d"], "hér": ["d"], "síðan": ["d"], "aptr": ["d"], "upp": ["d"], "út": ["d"],
             "inn": ["d"], "heim": ["d"], "braut": ["d"], "þegar": ["d", "c"], "unz": ["c"], "þótt": ["c"],
             "ef": ["c"], "nema": ["c"], "hvárki": ["c"], "bæði": ["c"], "sízt": ["d"], "mjök": ["d"]}

CLOSED = (
    _pron("ek", "p", "ek:s-n mik:s-a mér:s-d mín:s-g vit:d-n okkr:d-a/d-d okkar:d-g vér:p-n oss:p-a/p-d vár:p-g")
    + _pron("þú", "p", "þú:s-n þik:s-a þér:s-d/p-d þín:s-g þit:d-n ykkr:d-a/d-d ykkar:d-g þér:p-n ér:p-n "
                       "yðr:p-a/p-d yðar:p-g")
    + _pron("hann", "p", "hann:smn/sma honum:smd hans:smg")
    + _pron("hon", "p", "hon:sfn hón:sfn hana:sfa henni:sfd hennar:sfg")
    + _pron("sik", "p", "sik:s-a sér:s-d sín:s-g")
    + _pron("sá", "p", "sá:smn þann:sma þeim:smd/pmd/pfd/pnd þess:smg/sng sú:sfn þá:sfa/pma/pfa þeiri:sfd "
                       "þeirri:sfd þeirar:sfg þeirrar:sfg þat:snn/sna því:snd þeir:pmn þær:pfn/pfa þau:pnn/pna "
                       "þeira:pmg/pfg/png þeirra:pmg/pfg/png")
    + _pron("sjá", "p", "sjá:smn/sfn þessi:smn/sfn/pnn þenna:sma þessum:smd/pmd/pfd/pnd þessa:smg/sng/sfa/pma "
                        "þessar:sfg/pfn/pfa þessu:snd þetta:snn/sna þessir:pmn þessa:pmg")
    + _pron("hinn", "l", "hinn:smn/sma inn:smn/sma enn:smn/sma hinum:smd/pmd/pfd/pnd inum:smd enum:smd "
                         "hins:smg/sng ins:smg/sng ens:smg hin:sfn/pnn/pna in:sfn en:sfn hina:sfa/pma ina:sfa ena:sfa "
                         "hinni:sfd inni:sfd enni:sfd hinnar:sfg innar:sfg ennar:sfg hit:snn/sna it:snn/sna "
                         "et:snn/sna hinu:snd inu:snd enu:snd hinir:pmn inir:pmn enir:pmn hinar:pfn/pfa inar:pfn "
                         "hinna:pmg/pfg/png inna:pmg")
    + _pron("hverr", "p", "hverr:smn hvern:sma hverjum:smd hvers:smg/sng hver:sfn/pnn hverja:sfa/pma hverri:sfd "
                          "hverrar:sfg hvert:snn/sna hverju:snd hverir:pmn hverjar:pfn/pfa")
    + _pron("hvat", "p", "hvat:snn/sna hví:snd hvers:sng")
    + _pron("nökkurr", "p", "nökkurr:smn nökkurn:sma nökkurum:smd/pmd nökkurs:smg nökkur:sfn nökkura:sfa/pma "
                            "nökkut:snn/sna nökkuru:snd nökkurir:pmn")
    + _pron("engi", "p", "engi:smn/sfn/snn engan:sma engum:smd engis:smg enga:sfa engri:sfd ekki:snn/sna "
                         "einskis:sng engir:pmn")
    + _pron("einn", "m", "einn:smn einn:sma einum:smd eins:smg ein:sfn eina:sfa einni:sfd einnar:sfg eitt:snn/sna "
                         "einu:snd einir:pmn")
    + _poss("minn") + _poss("þinn") + _poss("sinn")
    + _pron("várr", "p", "várr:smn várn:sma várum:smd/pmd vár:sfn/pnn várt:snn/sna várir:pmn vára:pma/sfa")
    + _pron("maðr", "n", "maðr:smn mann:sma manni:smd manns:smg menn:pmn/pma mönnum:pmd manna:pmg "
                         "maðrinn:smn manninn:sma manninum:smd mannsins:smg mennirnir:pmn mennina:pma mönnunum:pmd")
    + _pron("mikill", "a", "mikill:smn mikinn:sma miklum:smd/pmd mikils:smg/sng mikil:sfn/pnn/pna mikla:sfa/pma "
                           "mikilli:sfd mikillar:sfg mikit:snn/sna miklu:snd miklir:pmn miklar:pfn/pfa mikla:smw "
                           "mikli:smn")
    + _pron("lítill", "a", "lítill:smn lítinn:sma litlum:smd/pmd lítils:smg/sng lítil:sfn/pnn litla:sfa/pma "
                           "lítilli:sfd lítillar:sfg lítit:snn/sna litlu:snd litlir:pmn")
    + _pron("annarr", "p", "annarr:smn annan:sma öðrum:smd/pmd/pfd/pnd annars:smg/sng önnur:sfn/pnn/pna aðra:sfa/pma "
                           "annarri:sfd annarrar:sfg annat:snn/sna öðru:snd aðrir:pmn aðrar:pfn/pfa annarra:pmg")
    + _pron("allr", "a", "allr:smn allan:sma öllum:smd/pmd/pfd/pnd alls:smg/sng öll:sfn/pnn/pna alla:sfa/pma "
                         "allri:sfd allrar:sfg allt:snn/sna alt:snn/sna öllu:snd allir:pmn allar:pfn/pfa allra:pmg/pfg")
    + _pron("báðir", "p", "báðir:pmn báða:pma báðar:pfn/pfa bæði:pnn/pna báðum:pmd beggja:pmg")
    + _pron("dóttir", "n", "dóttir:sfn dóttur:sfa/sfd/sfg dœtr:pfn/pfa dætr:pfn/pfa dœtrum:pfd dætrum:pfd dœtra:pfg")
    + _pron("móðir", "n", "móðir:sfn móður:sfa/sfd/sfg mœðr:pfn mæðr:pfn")
    + _pron("systir", "n", "systir:sfn systur:sfa/sfd/sfg systr:pfn/pfa systrum:pfd")
    + _pron("bróðir", "n", "bróðir:smn bróður:sma/smd/smg brœðr:pmn/pma bræðr:pmn/pma brœðrum:pmd bræðrum:pmd brœðra:pmg")
    + _pron("faðir", "n", "faðir:smn föður:sma/smd/smg feðr:pmn/pma feðrum:pmd feðra:pmg")
    + _pron("sonr", "n", "sonr:smn son:sma syni:smd sonar:smg synir:pmn sonu:pma sonum:pmd sona:pmg")
    + [(f, f, tag("m")) for f in "þrír fjórir fimm sex sjau átta níu tíu ellifu tólf tuttugu þrjátigi hundrað þúsund "
                                 "fyrsti annarr þriði þriðja þriðji fjórði fimmti sétti sjaundi átti níundi tíundi".split()]
    + _pron("tveir", "m", "tveir:pmn tvá:pma tvær:pfn/pfa tvau:pnn/pna tveim:pmd/pfd/pnd tveimr:pmd tveggja:pmg")
    + _pron("þrír", "m", "þrír:pmn þrjá:pma þrjár:pfn/pfa þrjú:pnn/pna þrim:pmd þrimr:pmd þriggja:pmg")
)
CLOSED_VERBS = {
    "vera": "em:1spi er:3spi ert:2spi erum:1ppi eruð:2ppi eru:3ppi var:3sei vart:2sei várum:1pei vórum:1pei "
            "váruð:2pei váru:3pei vóru:3pei sé:3sps sér:2sps séu:3pps væri:3ses værir:2ses væru:3pes verit:--e-p "
            "vera:--pn- ver:2spm",
    "hafa": "hefi:1spi hefir:3spi hefr:3spi höfum:1ppi hafið:2ppi hafa:3ppi hafði:3sei hafðir:2sei höfðum:1pei "
            "höfðu:3pei hafi:3sps hefði:3ses hefðu:3pes haft:--e-p hafa:--pn-",
    "munu": "mun:3spi munt:2spi munum:1ppi munu:3ppi mundi:3sei myndi:3ses mundu:3pei myndu:3pes muni:3sps",
    "skulu": "skal:3spi skalt:2spi skulum:1ppi skuluð:2ppi skulu:3ppi skyldi:3sei skyldu:3pei skyli:3sps",
    "vilja": "vil:1spi vill:3spi vilt:2spi viljum:1ppi vilið:2ppi vilja:3ppi vildi:3sei vildu:3pei vili:3sps",
    "eiga": "á:3spi átt:2spi eigum:1ppi eiguð:2ppi eigu:3ppi átti:3sei áttu:3pei eigi:3sps ætti:3ses",
    "kunna": "kann:3spi kannt:2spi kunnum:1ppi kunnu:3ppi kunni:3sei kunnu:3pei",
    "mega": "má:3spi mátt:2spi megum:1ppi megu:3ppi mátti:3sei máttu:3pei megi:3sps mætti:3ses",
    "vita": "veit:3spi veizt:2spi vitum:1ppi vitu:3ppi vissi:3sei vissu:3pei viti:3sps",
    "segja": "segi:1spi segir:3spi segjum:1ppi segja:3ppi sagði:3sei sögðu:3pei sagt:--e-p segi:3sps",
    "sjá": "sé:1spi sér:3spi sjám:1ppi sjá:3ppi sá:3sei sá:1sei sátt:2sei sám:1pei sáu:3pei sét:--e-p sjá:--pn-",
    "fá": "fæ:1spi fær:3spi fám:1ppi fá:3ppi fekk:3sei fékk:3sei fengu:3pei fengit:--e-p",
    "gera": "geri:1spi gerir:3spi gerum:1ppi gera:3ppi gerði:3sei gerðu:3pei gert:--e-p görði:3sei gørði:3sei "
            "gert:--e-p gört:--e-p gort:--e-p gørt:--e-p gera:--pn- göra:--pn- gøra:--pn-",
    "láta": "lét:3sei lét:1sei létu:3pei létum:1pei",
    "vera ": "vas:3sei vask:1sei",
    "verða": "verð:1spi verðr:3spi verðum:1ppi verða:3ppi varð:3sei urðu:3pei orðit:--e-p",
    "kveða": "kveð:1spi kveðr:3spi kvað:3sei kváðu:3pei kveðit:--e-p",
}
INDECLINABLE_POS = {"prep": "r", "conj": "c", "adv": "d", "interj": "i"}


def entries(zoega_path):
    """[(headword, pos, gender, info)] from Zoëga: info is the bracket after the
    headword (the inflection), pos one of n v a d r c i p."""
    out = []
    for e in json.load(open(zoega_path, encoding="utf-8")):
        hw = unicodedata.normalize("NFC", e["word"].strip())
        defs = [clean(d) for d in e["definitions"]]
        head = next((d for d in defs if not re.fullmatch(r"[IVX]+\)", d)), "")
        m = re.match(r"(\([^)]*\))?\s*,?\s*(.*)", head)
        info, rest = (m.group(1) or ""), m.group(2)
        pos = gender = None
        mm = re.match(r"(m|f|n)\.(?:\s*pl\.)?", rest)
        if mm:
            pos, gender = "n", mm.group(1)
        elif re.match(r"v\.", rest):
            pos = "v"
        elif re.match(r"a\.", rest):
            pos = "a"
        else:
            for word, p in INDECLINABLE_POS.items():
                if re.match(rf"{word}\.", rest):
                    pos = p
                    break
        if pos and re.match(rf"^[{on.LETTERS}]+$", hw):
            out.append((hw, pos, gender, info))
    return out


def name_forms(words, known=None):
    """Personal names are not in the dictionary: decline the ones the texts
    give in the nominative (Gunnarr, Flosi, Þorsteinn, Hallgerðr) by the
    commonest patterns, keeping only forms the texts also use."""
    caps = Counter(w for w in words if w[:1].isupper() and len(w) > 2 and on.fold(w) not in (known or ()))
    out, oblique = [], set()
    order = sorted(caps, key=lambda w: w.endswith("i"))         # strong names first: their oblique forms
    for w in order:
        if w.endswith("i") and w in oblique:
            continue
        pats = []
        if re.search(r"[^aeiouyáéíóúýæöøǫ]r$", w) and not w.endswith("rr"):
            s = w[:-1]                                           # Hrútr, Hallgerðr
            if re.search(r"(gerð|ríð|unn)r$", w):                 # women's names: Hallgerðr, Guðríðr, Unnr
                pats = [(s, "a", "f"), (s, "d", "f"), (s + "i", "d", "f"), (s + "ar", "g", "f")]
            else:
                pats = [(s, "a", "m"), (s + "i", "d", "m"), (s + "s", "g", "m")]
        elif w.endswith("rr"):                                   # Gunnarr
            s = w[:-1]
            pats = [(s, "a", "m"), (s + "i", "d", "m"), (s + "s", "g", "m")]
        elif re.search(r"[aeiouyáéíóúý](nn|ll)$", w):           # Þorsteinn, Njáll
            s = w[:-1]
            pats = [(s, "a", "m"), (s + "i", "d", "m"), (s + "s", "g", "m")]
        elif w.endswith("i"):                                    # Flosi, Atli
            s = w[:-1]
            pats = [(s + "a", "a", "m"), (s + "a", "d", "m"), (s + "a", "g", "m")]
        if not pats:
            continue
        out.append((w, w, tag("n", number="s", gender="f" if re.search(r"(gerð|ríð|unn)r$", w) else "m", case="n")))
        for f, c, g in pats:
            if caps.get(f):
                out.append((f, w, tag("n", number="s", gender=g, case=c)))
                oblique.add(f)
    return out


# short forms (one or two letters) that are real: the rest are generator debris
SHORT_OK = {(lemma, form) for form, lemma, _ in CLOSED if len(form) < 3} | {
    ("vera", "er"), ("eiga", "á"), ("mega", "má"), ("sjá", "sé"), ("fá", "fæ"), ("hinn", "in"), ("hinn", "it"),
    ("hinn", "en"), ("hinn", "et"), ("ek", "ek"), ("sá", "sú")}


class Analyser:
    """Readings for each written form, ranked: [(lemma, key, tag)]."""

    def __init__(self, table):
        self.table = table                 # {fold(form): {(lemma, key, tag)}}
        self.weight = Counter()

    @classmethod
    def build(cls, zoega_path, words=None):
        """The table for the forms in words (all generated forms if None)."""
        want = {on.fold(w) for w in words} if words is not None else None
        table = defaultdict(set)

        def put(form, lemma, t):
            # a generated form must be a word (a missing principal part, "-", leaves bare endings)
            if not form or (len(form) < 3 and form != lemma and (lemma, form) not in SHORT_OK) \
                    or not re.fullmatch(rf"[{on.LETTERS}]+", form):
                return
            k = on.fold(form)
            if want is None or k in want:
                table[k].add((lemma, on.key(lemma), t))
        for hw, pos, gender, info in entries(zoega_path):
            if pos == "n":
                forms = noun_forms(hw, gender, info)
            elif pos == "a":
                forms = adjective_forms(hw, info)
            elif pos == "v":
                forms = verb_forms(hw, info)
            else:
                forms = [(hw, tag(pos))]
            for f, t in forms:
                put(f, hw, t)
        for form, lemma, t in CLOSED:
            put(form, lemma, t)
        for lemma, rows in CLOSED_VERBS.items():
            lemma = lemma.strip()
            for item in rows.split():
                form, spec = item.split(":")
                p, n, te, mo = spec[0], spec[1], spec[2], spec[3]
                put(form, lemma, tag("t" if mo == "p" else "v", person=p, number=n, tense=te, mood=mo))
        for form, poss in PARTICLES.items():
            for p in poss:
                put(form, form, tag(p))
        if words is not None:
            for form, lemma, t in name_forms(words, set(table)):
                put(form, lemma, t)
        return cls(table)

    describe = staticmethod(describe)

    def candidates(self, word):
        k = on.fold(word)
        return self.table.get(k) or (self.table.get(k.replace("o", "ö")) if "o" in k else None) or set()

    def train(self, words, rounds=4):
        """Lemma weights by EM over all tokens."""
        cands = [self.candidates(w) for w in words]
        weight = Counter()
        for _ in range(rounds):
            new = Counter()
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
        cs = self.candidates(word)
        if not cs:
            return []
        lemma_w = self.weight

        def pref(t):
            return ("vnaplrcdgtmi".find(t[0]) if t[0] in "vnaplrcdgtmi" else 20, t[1] != "3", t)
        ranked = sorted(cs, key=lambda c: (-lemma_w[c[1]], c[0], pref(c[2])))
        # one reading per (lemma, tag); the most likely lemma's readings first
        return ranked[:limit]
