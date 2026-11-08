"""Sanskrit helpers: transliteration (SLP1, Devanagari -> IAST), the Digital
Corpus of Sanskrit's CoNLL-U files, readable parses from its features, and
splitting its sandhi groups into the words a printed IAST text separates.

DCS (Oliver Hellwig, CC BY 4.0) writes each sandhi group as a multiword token
("buddhirjanārdana" = buddhiḥ + janārdana). Printed IAST texts separate words
wherever sandhi only changed a word's last or first letter ("buddhir
janārdana") and join them where vowels fused ("caiva" = ca + eva) and within
compounds ("aśrupūrṇākulekṣaṇam"). `split_group` does the same, so each piece
shown is a tap target; a piece holding several words shows them as "the parts
of this word", like Coptic and Hebrew.

Lemma keys are "san:" + the DCS lemma in IAST ("san:karman", "san:vac").
"""
import re
import unicodedata

PREFIX = "san:"


def lemma_key(lemma):
    return PREFIX + unicodedata.normalize("NFC", lemma) if lemma and lemma != "_" else None


def is_sanskrit_key(k):
    return bool(k) and k.startswith(PREFIX)


# ---------------------------------------------------------------- transliteration

SLP1 = {
    "A": "ā", "I": "ī", "U": "ū", "f": "ṛ", "F": "ṝ", "x": "ḷ", "X": "ḹ", "E": "ai", "O": "au",
    "M": "ṃ", "H": "ḥ", "~": "m̐", "K": "kh", "G": "gh", "N": "ṅ", "C": "ch", "J": "jh", "Y": "ñ",
    "w": "ṭ", "W": "ṭh", "q": "ḍ", "Q": "ḍh", "R": "ṇ", "T": "th", "D": "dh", "P": "ph", "B": "bh",
    "S": "ś", "z": "ṣ", "L": "ḻ", "|": "ḻh",
}


def slp1_to_iast(s):
    s = re.sub(r"[/\\^]", "", s)            # accents
    return "".join(SLP1.get(c, c) for c in s)


IAST_SLP1 = [("ai", "E"), ("au", "O"), ("kh", "K"), ("gh", "G"), ("ch", "C"), ("jh", "J"), ("ṭh", "W"),
             ("ḍh", "Q"), ("th", "T"), ("dh", "D"), ("ph", "P"), ("bh", "B"), ("ā", "A"), ("ī", "I"),
             ("ū", "U"), ("ṛ", "f"), ("ṝ", "F"), ("ḷ", "x"), ("ḹ", "X"), ("ṃ", "M"), ("ḥ", "H"), ("ṅ", "N"),
             ("ñ", "Y"), ("ṭ", "w"), ("ḍ", "q"), ("ṇ", "R"), ("ś", "S"), ("ṣ", "z"), ("m̐", "~")]


def iast_to_slp1(s):
    s = unicodedata.normalize("NFC", s)
    for a, b in IAST_SLP1:
        s = s.replace(a, b)
    return s


DEVA_VOWELS = {"अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū", "ऋ": "ṛ", "ॠ": "ṝ", "ऌ": "ḷ",
               "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au"}
DEVA_SIGNS = {"ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū", "ृ": "ṛ", "ॄ": "ṝ", "ॢ": "ḷ", "े": "e",
              "ै": "ai", "ो": "o", "ौ": "au"}
DEVA_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ", "च": "c", "छ": "ch", "ज": "j", "झ": "jh",
             "ञ": "ñ", "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ", "त": "t", "थ": "th", "द": "d",
             "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
             "ल": "l", "ळ": "ḻ", "व": "v", "श": "ś", "ष": "ṣ", "स": "s", "ह": "h"}
DEVA_OTHER = {"ॐ": "oṃ", "ं": "ṃ", "ः": "ḥ", "ँ": "m̐", "ऽ": "'", "।": "|", "॥": "||", "्": ""}


def deva_to_iast(text):
    out, i = [], 0
    digits = "०१२३४५६७८९"
    while i < len(text):
        c = text[i]
        if c in DEVA_CONS:
            out.append(DEVA_CONS[c])
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt == "्":
                i += 2
                continue
            if nxt in DEVA_SIGNS:
                out.append(DEVA_SIGNS[nxt])
                i += 2
                continue
            out.append("a")
        elif c in DEVA_VOWELS:
            out.append(DEVA_VOWELS[c])
        elif c in DEVA_OTHER:
            out.append(DEVA_OTHER[c])
        elif c in digits:
            out.append(str(digits.index(c)))
        else:
            out.append(c)
        i += 1
    t = "".join(out)
    t = re.sub(r"([āīū])'+", r"\1", t)
    return t


def letters(s):
    """For aligning two editions: lower case, letters only, nasals merged
    (ṃ/ṅ/ñ/ṇ/m/n all differ between printings)."""
    s = unicodedata.normalize("NFC", s.lower())
    return "".join("m" if c in "ṃṅñṇmn" else c for c in s if c.isalpha())


# ---------------------------------------------------------------- DCS CoNLL-U

def read_conllu(path, counters=False):
    """[{id, text, groups: [{form, words: [word]}]}]; a word is a dict of
    form, lemma, upos, feats (dict), misc (dict)."""
    sents, cur, span, text = [], None, None, ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("# sent_id"):            # (its "# text" comes just before)
                cur = {"id": line.split("=", 1)[1].strip(), "text": text, "groups": []}
                sents.append(cur)
                span, text = None, ""
            elif line.startswith("# text"):
                text = line.split("=", 1)[1].strip()
            elif line.startswith("# sent_counter") and cur is not None:
                cur["counter"] = line.split("=", 1)[1].strip()      # a verse/section number, in some chapters
            elif line and line[0].isdigit() and cur is not None:
                c = line.split("\t")
                if "-" in c[0]:
                    a, b = map(int, c[0].split("-"))
                    span = (a, b)
                    cur["groups"].append({"form": nfc(c[1]), "words": []})
                    continue
                if "." in c[0]:
                    continue
                n = int(c[0])
                lemma = nfc(c[2]).replace("ﾱ", "ḷ").replace("\uffde", "ṝ")      # (DCS mojibake: kḷp, āpṝ)
                w = {"form": nfc(c[1]), "lemma": lemma, "upos": c[3], "feats": kv(c[5]), "misc": kv(c[9])}
                if span and span[0] <= n <= span[1]:
                    cur["groups"][-1]["words"].append(w)
                else:
                    span = None
                    cur["groups"].append({"form": w["form"], "words": [w]})
    for s in sents:
        s["groups"] = _with_unannotated(s)
    return sents


def _with_unannotated(sent):
    """DCS sometimes leaves a word of the sentence's text unannotated (13.11
    "proktam ajñānaṃ"): add such words, in place, as groups with no words."""
    text = sent["text"].split()
    groups = sent["groups"]
    if not text or not groups:
        return groups
    out, gi = [], 0
    for t in text:
        t = nfc(t)
        if gi < len(groups) and groups[gi]["form"] == t:
            out.append(groups[gi])
            gi += 1
        elif gi < len(groups) and any(g["form"] == t for g in groups[gi:gi + 3]):
            while groups[gi]["form"] != t:          # (annotated words missing from the text)
                out.append(groups[gi])
                gi += 1
            out.append(groups[gi])
            gi += 1
        else:
            out.append({"form": t, "words": []})
    out.extend(groups[gi:])
    if sum(1 for g in out if g["words"]) < len(groups):  # couldn't follow the text: keep DCS's groups
        return groups
    return out


def nfc(s):
    return unicodedata.normalize("NFC", s)


def kv(s):
    if not s or s == "_":
        return {}
    return dict(p.split("=", 1) for p in s.split("|") if "=" in p)


# ---------------------------------------------------------------- sandhi groups

BOUND = {"a", "an", "su", "dus", "dur", "duṣ", "duḥ", "sa", "sam", "nis", "nir", "niḥ"}


def is_bound(w):
    """A word that can't end a printed word: a compound member, or the
    negative prefix a-/an-."""
    if w["feats"].get("Case") == "Cpd":
        return True
    return w["upos"] in ("PART", "ADV", "ADP") and w["lemma"] in BOUND and w["form"] in BOUND


def _unsandhied(w):
    return nfc(w["misc"].get("Unsandhied") or w["form"])


def _same_word(piece, word):
    """`piece` is `word` as written before the next word: equal except for
    its last letter or two (buddhir/buddhiḥ, karmaṇas/karmaṇaḥ, ced/cet,
    tam/taṃ, tān/tāṃs)."""
    if piece.startswith("'") and word.startswith("a"):        # avagraha: śreyo 'ham = aham
        piece, word = piece[1:], word[1:]
    if not piece or not word:
        return False
    k = 0
    while k < min(len(piece), len(word)) and piece[k] == word[k]:
        k += 1
    if len(piece) - k > 2:
        return False
    if k >= len(word) - 1:
        return True
    # -aḥ written -o (rāmo gacchati), -as written -o
    return word.endswith("aḥ") and piece.endswith("o") and k >= len(word) - 2


INITIAL = {"ś": ("ch",), "h": ("gh", "dh", "bh", "ḍh", "jh")}
VOWELS = set("aāiīuūṛṝḷeo")


def _starts_word(rest, word):
    """`rest` begins with `word` as written after the previous word (its
    second letter may have fused with a following short word: ca + a- = cā)."""
    w = word.lstrip("'")
    rest = rest.lstrip("'")
    if not w or not rest:
        return False
    heads = (w[0],) + INITIAL.get(w[0], ())
    for h in heads:
        if not rest.startswith(h):
            continue
        r2, w2 = rest[len(h):len(h) + 1], w[1:2]
        if not w2 or r2 == w2 or (r2 in VOWELS and w2 in VOWELS):
            return True
    return False


def _ends_with_word(form, start, k, word):
    """form[start:k] ends with `word` as written before another word; when
    other words precede it in the piece, its first vowel may have fused with
    theirs (indriya + artha = indriyārtha, paśya + etān = paśyaitān)."""
    for j in range(start, k):
        tail = form[j:k]
        if _same_word(tail, word):
            if j == start or len(word) > 1:
                return True
        if j > start and word[0] in VOWELS and form[j] in VOWELS:
            for m in (1, 2):
                if j + m <= k and all(c in VOWELS for c in form[j:j + m]) and _same_word(form[j + m:k], word[1:]):
                    return True
    return False


def split_group(form, words):
    """A DCS sandhi group -> [(piece, [word index…])]: the pieces a printed
    IAST text would separate with spaces."""
    if len(words) <= 1:
        return [(form, list(range(len(words))))]
    pieces, start, owned = [], 0, []
    for i, w in enumerate(words):
        owned.append(i)
        if i == len(words) - 1:
            break
        if is_bound(w):
            continue
        u, nxt = _unsandhied(w), _unsandhied(words[i + 1])
        cut = None
        for k in range(start + 1, len(form)):
            piece_end = form[start:k]
            # a final vowel can't vanish before the next word: that is fusion (parayā + āviṣṭaḥ)
            if not _ends_with_word(form, start, k, u):
                continue
            if u[-1] in VOWELS and not form[:k].endswith(u[-1]) and not (u[-1] in "iīuūṛ" and form[k - 1] in "yvr"):
                if not (u[-1] in "eo" and form[k - 1] == "a"):        # -e/-o before a vowel: -a
                    continue
            if _starts_word(form[k:], nxt):
                cut = k
                break
        if cut is None:
            continue
        pieces.append((form[start:cut], owned))
        start, owned = cut, []
    pieces.append((form[start:], owned))
    return pieces


# ---------------------------------------------------------------- parses

POS = {"NOUN": "noun", "ADJ": "adjective", "PRON": "pronoun", "NUM": "numeral", "ADV": "adverb",
       "PART": "particle", "CONJ": "conjunction", "CCONJ": "conjunction", "SCONJ": "subordinating conjunction",
       "INTJ": "interjection", "ADP": "preposition", "VERB": "verb", "PROPN": "proper noun"}
CASE = {"Nom": "nominative", "Acc": "accusative", "Ins": "instrumental", "Dat": "dative", "Abl": "ablative",
        "Gen": "genitive", "Loc": "locative", "Voc": "vocative"}
GENDER = {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter"}
NUMBER = {"Sing": "singular", "Dual": "dual", "Plur": "plural"}
PERSON = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
TENSE = {"Pres": "present", "Past": "past", "Impf": "imperfect", "Fut": "future", "Aor": "aorist", "Perf": "perfect"}
MOOD = {"Ind": "indicative", "Imp": "imperative", "Opt": "optative", "Jus": "injunctive", "Cond": "conditional",
        "Sub": "subjunctive", "Prec": "precative"}


def describe(w):
    f = w["feats"]
    pos = w["upos"]
    out = []
    if f.get("Case") == "Cpd":
        out = ["compound member", "(stem)"]
        if pos == "VERB" and f.get("VerbForm") == "Part":
            out[0] = f"{TENSE.get(f.get('Tense'), '')} participle, compound member".strip()
        return " · ".join(out)
    if pos == "VERB":
        vf = f.get("VerbForm")
        if vf == "Part":
            out = [f"{TENSE.get(f.get('Tense'), '')} participle".strip()]
        elif vf == "Gdv":
            out = ["gerundive"]
        elif vf == "Conv":
            return "absolutive (indeclinable participle)"
        elif vf == "Inf":
            return "infinitive"
        else:
            tense = TENSE.get(f.get("Tense"), "")
            if f.get("Formation") == "peri":
                tense = f"periphrastic {tense}".strip()
            out = ["verb", tense, MOOD.get(f.get("Mood"), "")]
            if f.get("Voice") == "Pass":
                out.append("passive")
            out += [PERSON.get(f.get("Person"), ""), NUMBER.get(f.get("Number"), "")]
            return " · ".join(x for x in out if x)
        if f.get("Voice") == "Pass" and vf == "Part" and f.get("Tense") == "Pres":
            out.append("passive")
    else:
        out = [POS.get(pos, pos.lower())]
    out += [CASE.get(f.get("Case"), ""), GENDER.get(f.get("Gender"), ""), NUMBER.get(f.get("Number"), "")]
    return " · ".join(x for x in out if x)


def agdt(w):
    """A 9-character AGDT-style tag (part of speech only), for the function-word flag."""
    p = {"NOUN": "n", "PROPN": "n", "ADJ": "a", "PRON": "p", "NUM": "m", "VERB": "v", "ADV": "d", "PART": "g",
         "CONJ": "c", "CCONJ": "c", "SCONJ": "c", "INTJ": "i", "ADP": "r"}.get(w["upos"], "-")
    if w["upos"] == "VERB" and w["feats"].get("VerbForm") == "Part":
        p = "t"
    return p + "-" * 8


def main_word(words):
    """The word a group's lemma comes from: the last that isn't a particle
    or conjunction tacked on (ca, eva, iti), else the last."""
    for i in range(len(words) - 1, -1, -1):
        if words[i]["upos"] not in ("PART", "CONJ", "CCONJ") and words[i]["feats"].get("Case") != "Cpd":
            return i
    for i in range(len(words) - 1, -1, -1):
        if words[i]["feats"].get("Case") != "Cpd":
            return i
    return len(words) - 1


# ---------------------------------------------------------------- dictionaries

# DCS lemma spellings the Cologne dictionaries list under another headword
ALIASES = {"enad": ["ena"], "kaścit": ["kim", "cit"], "kaścana": ["kim", "cana"], "kaccit": ["kaccit", "kad"],
           "oṃ": ["om"], "kiṃcid": ["kiMcid", "kim"]}
PREVERBS = sorted("ati adhi anu antar apa api abhi ava ā ud ut upa dus dur nis nir ni parā pari pra prati vi sam saṃ"
                  .split(), key=len, reverse=True)


def causative_roots(base):
    """A causative stem without -ay -> roots it may come from (MW lists
    causatives under the root): bhāv -> bhū, darś -> dṛś, moh -> muh,
    sthāp -> sthā, kār -> kṛ, nāś -> naś, varj -> vṛj."""
    out = [base]
    if base.endswith("āp"):
        out.append(base[:-1])
    for a, b in (("āv", "ū"), ("ār", "ṛ"), ("ar", "ṛ"), ("o", "u"), ("e", "i"), ("ā", "a"), ("au", "ū"), ("ai", "ī")):
        i = base.rfind(a)
        if i >= 0:
            out.append(base[:i] + b + base[i + len(a):])
    return out


def candidates(lemma, verb=True):
    """A DCS lemma -> Cologne headwords (SLP1) to try, best first: the lemma;
    -ant/-mant/-vant stems as -at/-mat/-vat (bhagavant -> Bagavat);
    causative and denominative -ay verbs under their root; preverbs stripped
    (samupasthā -> upasthā -> sthā) -- for verbs only: a noun's prefix is
    part of its meaning (nirvāṇa is not vāṇa)."""
    l = nfc(lemma)
    out = [l] + ALIASES.get(l, [])
    for a, b in (("mant", "mat"), ("vant", "vat"), ("ant", "at")):
        if l.endswith(a):
            out.append(l[:-len(a)] + b)
            break
    if verb and l.endswith("ay") and len(l) > 3:
        out += [l + "a"] + causative_roots(l[:-2])
    if l.endswith("am") and len(l) > 4:              # adverbs: nityam, satatam -> nitya, satata
        out.append(l[:-1])
    stem = l
    for _ in range(3 if verb else 0):
        nxt = None
        for p in PREVERBS:
            if stem.startswith(p) and len(stem) > len(p) + 1:
                nxt = [stem[len(p):]]
                if nxt[0].startswith("ṇ"):                  # praṇaś = pra + naś
                    nxt.insert(0, "n" + nxt[0][1:])
                break
            # a vowel-final preverb fused with the root's first vowel (prāp = pra + āp, upe = upa + i)
            if p[-1] in "ai" and len(p) > 1 and stem.startswith(p[:-1]) and len(stem) >= len(p):
                c, rest = stem[len(p) - 1], stem[len(p):]
                fused = {"ā": ["ā", "a"], "e": ["i", "ī"], "o": ["u", "ū"], "ī": ["i", "ī"], "y": ["i"]}.get(c)
                if p[-1] == "i" and c == "y":            # vyavasā = vi + avasā
                    nxt = [rest]
                elif fused and p[-1] == "a":
                    nxt = [v + rest for v in fused]
                elif p[-1] == "i" and c == "ī":
                    nxt = ["i" + rest, "ī" + rest]
                if nxt:
                    break
        if p in ("ut", "ud") and stem.startswith("utth"):         # ut + sthā
            nxt = ["s" + stem[2:]]
        if not nxt:
            break
        out += nxt
        stem = nxt[0]
        if stem.endswith("ay") and len(stem) > 3:
            out += causative_roots(stem[:-2])
    seen, res = set(), []
    for c in out:
        s = c if re.search(r"[A-Z]", c) else iast_to_slp1(c)
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res


def iter_cologne(path):
    """(L, k1, body) for each record of a csl-orig dictionary file."""
    rec = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("<L>"):
                m = re.search(r"<k1>([^<]+)", line)
                rec = [line.split("<pc>")[0][3:], m.group(1) if m else "", []]
            elif line.startswith("<LEND>"):
                if rec:
                    yield rec[0], rec[1], "\n".join(rec[2])
                rec = None
            elif rec is not None:
                rec[2].append(line.rstrip("\n"))


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_html(body):
    """Macdonell: {#…#} SLP1 headword, {@…@} bold IAST, {%…%} italic, <lex> grammar."""
    b = body.replace("🞄", "").replace("‿", "-")
    b = re.sub(r"\{#(.*?)#\}", lambda m: "<b>" + slp1_to_iast(m.group(1)) + "</b>", b)
    b = re.sub(r"\{@(.*?)@\}", r"<b>\1</b>", b)
    b = re.sub(r"\{%(.*?)%\}", r"<i>\1</i>", b)
    b = re.sub(r"<lex>(.*?)</lex>", r"<i>\1</i>", b)
    b = re.sub(r"<(?!/?[bi]>)[^>]+>", "", b)
    b = b.replace("¦", "")
    return "<p>" + " ".join(b.split()) + "</p>"


def mw_html(body):
    """Monier-Williams: <s>…</s> SLP1 Sanskrit, <ls> sources (small), <lex>
    grammar (italic); other markup dropped."""
    b = re.sub(r"<info[^>]*/>|<srs/>|<pcol>.*?</pcol>|<pb[^>]*/>", "", body)
    b = re.sub(r"<s>(.*?)</s>", lambda m: "<b>" + slp1_to_iast(m.group(1)).replace("˚", "–") + "</b>", b)
    b = re.sub(r"\{#(.*?)#\}", lambda m: "<b>" + slp1_to_iast(m.group(1)) + "</b>", b)
    b = re.sub(r"\{%(.*?)%\}", r"<i>\1</i>", b)
    b = re.sub(r"<ls[^>]*>(.*?)</ls>", r'<span class="src">\1</span>', b)
    b = re.sub(r"<lex[^>]*>(.*?)</lex>", r"<i>\1</i>", b)
    b = re.sub(r"<hom>(.*?)</hom>", r"\1", b)
    b = re.sub(r"<(?!/?(?:b|i|span)\b)[^>]+>", "", b)
    b = b.replace("¦", "—")
    return " ".join(b.split())


# DCS's dictionary mixes in a few German glosses
GERMAN = {"gleicher", "angemessen", "gedeihen", "huldigen", "menschenfreundlich", "unerforschlich", "verehren",
          "verleihen", "vernichten", "verkünden"}


def short_gloss(meanings, limit=90):
    """DCS dictionary meanings ("act; action; performance; …") -> a short gloss."""
    parts = [p.strip() for p in meanings.split(";")
             if p.strip() and not re.search(r"[￼äöüß]", p) and p.strip() not in GERMAN]
    out = ""
    for p in parts:
        if out and len(out) + len(p) + 2 > limit:
            break
        out = f"{out}, {p}" if out else p
    return out
