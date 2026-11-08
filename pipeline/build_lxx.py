"""Add the Septuagint to texts.db: Swete's Greek text (First1KGreek
transcription, via nathans/lxx-swete), parsed with Morpheus, and the Updated
Brenton English Septuagint (CC0) as the English.

Usage: python build_lxx.py <lxx-swete repo> <brenton repo> <treebank dir> <texts.db> [macula tsv] [shortdefs]

Like the New Testament (build_nt.py): a work per book (author "Septuagint",
form "bible"), a part per chapter, a block per verse, cited "chapter.verse"
("4.34a" for Swete's lettered verses). Brenton's paragraph and poetry marks
give the Greek its paragraphs (and verse-per-line poetry).

English verses are matched to Greek verses by number; where the two number a
stretch differently, the verses in between are paired in order (proportionally
when the counts differ). Brenton translates Theodotion's Daniel, Susanna and
Bel, so the Old Greek versions of those have no English; Swete has no
Ecclesiastes in this transcription, and Brenton has no Odes or Psalms of
Solomon.

The transcription is OCR'd and has some errors (a few hundred words with Latin
letters, e.g. "γυmῖκα"); Morpheus leaves those unparsed.
"""
import csv
import difflib
import glob
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

import greek
import morpheus
from build_texts import lemma_frequency, tokens_for

# Swete file stem -> (Brenton book code or None, English title)
BOOKS = [
    ("01.Genesis", "GEN", "Genesis"), ("02.Exodus", "EXO", "Exodus"), ("03.Leviticus", "LEV", "Leviticus"),
    ("04.Numeri", "NUM", "Numbers"), ("05.Deuteronomium", "DEU", "Deuteronomy"),
    ("06.Josue", "JOS", "Joshua"), ("08.Judices", "JDG", "Judges"), ("10.Ruth", "RUT", "Ruth"),
    ("11.Regnorum_I", "1SA", "1 Kingdoms (1 Samuel)"), ("12.Regnorum_II", "2SA", "2 Kingdoms (2 Samuel)"),
    ("13.Regnorum_III", "1KI", "3 Kingdoms (1 Kings)"), ("14.Regnorum_IV", "2KI", "4 Kingdoms (2 Kings)"),
    ("15.Paralipomenon_I", "1CH", "1 Chronicles"), ("16.Paralipomenon_II", "2CH", "2 Chronicles"),
    ("17.Esdras_A", "1ES", "1 Esdras"), ("18.Esdras_B", "EZR", "2 Esdras (Ezra–Nehemiah)"),
    ("19.Esther", "ESG", "Esther"), ("20.Judith", "JDT", "Judith"), ("21.Tobias", "TOB", "Tobit"),
    ("23.Machabaeorum_i", "1MA", "1 Maccabees"), ("24.Machabaeorum_ii", "2MA", "2 Maccabees"),
    ("25.Machabaeorum_iii", "3MA", "3 Maccabees"), ("26.Machabaeorum_iv", "4MA", "4 Maccabees"),
    ("27.Psalmi", "PSA", "Psalms"), ("28.Odae", None, "Odes"), ("29.Proverbia", "PRO", "Proverbs"),
    ("31.Canticum", "SNG", "Song of Songs"), ("32.Job", "JOB", "Job"),
    ("33.Sapientia_Salomonis", "WIS", "Wisdom of Solomon"), ("34.Ecclesiasticus", "SIR", "Sirach"),
    ("35.Psalmi_Salomonis", None, "Psalms of Solomon"),
    ("36.Osee", "HOS", "Hosea"), ("37.Amos", "AMO", "Amos"), ("38.Michaeas", "MIC", "Micah"),
    ("39.Joel", "JOL", "Joel"), ("40.Abdias", "OBA", "Obadiah"), ("41.Jonas", "JON", "Jonah"),
    ("42.Nahum", "NAM", "Nahum"), ("43.Habacuc", "HAB", "Habakkuk"), ("44.Sophonias", "ZEP", "Zephaniah"),
    ("45.Aggaeus", "HAG", "Haggai"), ("46.Zacharias", "ZEC", "Zechariah"), ("47.Malachias", "MAL", "Malachi"),
    ("48.Isaias", "ISA", "Isaiah"), ("49.Jeremias", "JER", "Jeremiah"), ("50.Baruch", "BAR", "Baruch"),
    ("51.Threni_seu_Lamentationes", "LAM", "Lamentations"), ("52.Epistula_Jeremiae", "LJE", "Letter of Jeremiah"),
    ("53.Ezechiel", "EZK", "Ezekiel"),
    ("54.Susanna_translatio_Graeca", None, "Susanna (Old Greek)"),
    ("55.Susanna_Theodotionis_versio", "SUS", "Susanna (Theodotion)"),
    ("56.Daniel_translatio_Graeca", None, "Daniel (Old Greek)"),
    ("57.Daniel_Theodotionis_versio", "DAG", "Daniel (Theodotion)"),
    ("58.Bel_et_Draco_translatio_Graeca", None, "Bel and the Dragon (Old Greek)"),
    ("59.Bel_et_Draco_Theodotionis_versio", "BEL", "Bel and the Dragon (Theodotion)"),
]
URN = "urn:cts:greekLit:tlg0527.tlg{:03d}"
CREDIT = ("Greek: H. B. Swete, The Old Testament in Greek according to the Septuagint (1909–1930), "
          "transcribed by the Open Greek and Latin Project's First1KGreek (CC BY-SA 4.0). Parses: Morpheus "
          "(automatic). English: Updated Brenton English Septuagint (L. C. L. Brenton 1851; updates by "
          "Adam Boyd 2020), CC0.")


def u16(text, i):
    return len(text[:i].encode("utf-16-le")) // 2


def read_swete(path):
    """[(chapter, verse, text)] in order; words joined with spaces."""
    verses, current = [], None
    for line in open(path, encoding="utf-8"):
        ref, _, word = line.rstrip("\n").partition(" ")
        parts = ref.split(".")
        if len(parts) < 3 or not word:
            continue
        key = (parts[1], parts[2])
        if current is None or current[0] != key:
            current = (key, [])
            verses.append(current)
        current[1].append(word)
    # A title the transcription labels with the previous verse number (Psalm
    # 14's title as "14.7", before 14.1): it belongs to the chapter's verse 1.
    def num(v):
        m = re.match(r"\d+", v)
        return int(m.group()) if m else 0
    merged = []
    for i, ((c, v), words) in enumerate(verses):
        nxt = verses[i + 1][0] if i + 1 < len(verses) else None
        prev = verses[i - 1][0] if i else None
        if nxt and nxt[0] == c and num(v) > num(nxt[1]) and (prev is None or prev[0] != c):
            verses[i + 1] = (nxt, words + verses[i + 1][1])
            continue
        merged.append(((c, v), words))
    verses = merged
    out = []
    for (c, v), words in verses:
        text = " ".join(words)
        text = re.sub(r"\s+([,.;·:!])", r"\1", text)      # "με ;" -> "με;"
        text = re.sub(r"\s*\(\d+\)\s*", " ", text).strip()  # Swete's other numbering, "(2)"
        text = re.sub(r"(?<!\S)\d+(?!\S)\s*", "", text)               # stray verse numbers "1 Πᾶν"
        text = re.sub(r"(?<![\w])[0-9a-z](?=[\u0370-\u03ff\u1f00-\u1fff])", "", text)   # "1Καὶ", "aγέγραπται"
        out.append((c, v, fix_marks(text)))
    return out


def fix_marks(text):
    """The transcription writes elision and some breathings with the spacing
    marks ᾿ ῾ ʼ: "δι᾿" -> "διʼ" (as in our other texts), "᾿Ισραήλ" -> "Ἰσραήλ"."""
    text = re.sub(r"(?<=\w)[᾿’](?!\w)", "\u02bc", text)
    text = re.sub(r"[᾿](\w)", lambda m: unicodedata.normalize("NFC", m.group(1) + "\u0313"), text)
    text = re.sub(r"[῾](\w)", lambda m: unicodedata.normalize("NFC", m.group(1) + "\u0314"), text)
    return text


# Koine spellings Morpheus (Attic) doesn't know: λήμψεται for λήψεται
KOINE = [("λημψ", "ληψ"), ("λημφ", "ληφ"), ("Λημψ", "Ληψ"), ("λήμψ", "λήψ"), ("λήμφ", "λήφ")]


def koine_variants(form):
    out = []
    for a, b in KOINE:
        if a in form:
            out.append(form.replace(a, b))
    return out


USFM_INLINE = re.compile(r"\\\+?(add|sc|it|nd|w|wj|bd|em)\*?")


def read_brenton(path):
    """[(chapter, verse, text, mark)] where mark is "p" (a paragraph starts at
    this verse), "q" (a poetry line) or ""."""
    verses = []
    chapter, mark = None, ""
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        m = re.match(r"\\(\w+)\s*(.*)", line)
        if not m:
            if verses and line:
                verses[-1][2] += " " + line
            continue
        tag, rest = m.groups()
        if tag == "c":
            chapter = rest.split()[0]
            mark = "p"
        elif tag in ("p", "m", "b", "nb", "d"):
            mark = mark or "p"
            if rest and verses:
                verses[-1][2] += " " + rest
        elif tag == "q1":
            if rest.startswith("\\v"):
                mark = mark or "q"
                tag, rest = "v", rest[3:]
            elif rest and verses:
                verses[-1][2] += " " + rest
                continue
            else:
                mark = mark or "q"
                continue
        if tag == "v" and chapter:
            num, _, text = rest.partition(" ")
            verses.append([chapter, num, text, mark])
            mark = ""
    out = []
    for c, v, text, mark in verses:
        text = USFM_INLINE.sub("", text)
        text = re.sub(r"\\f .*?\\f\*", "", text)
        out.append((c, v, re.sub(r"\s+", " ", text).strip(), mark))
    return out


def pair(greek_verses, english_verses):
    """English verse indices for each Greek verse.

    Swete and Brenton number some stretches differently (Joel 2:28-32 is
    Brenton's 3:1-5; Jeremiah, Proverbs, Esther's additions …), so matching by
    number alone pairs the wrong verses. Instead, a dynamic-programming
    alignment of the two verse sequences (in the manner of Gale & Church's
    sentence alignment): verses of matching length pair cheaply, the same
    verse number is a bonus, and one Greek verse may take two English verses
    (or the reverse) or none."""
    import math
    G = [len(t) for _, _, t in greek_verses]
    E = [len(t) for _, _, t, _ in english_verses]
    gk = [f"{c}.{v}" for c, v, _ in greek_verses]
    ek = [f"{c}.{v}" for c, v, _, _ in english_verses]
    n, m = len(G), len(E)
    ratio = (sum(E) + 1) / (sum(G) + 1)

    def lc(lg, le):
        return abs(math.log((le + 20) / (ratio * lg + 20))) * 2.0

    INF = float("inf")
    band = max(80, abs(n - m) + 40)
    cost = {(0, 0): 0.0}
    back = {}
    for i in range(n + 1):
        centre = i * m / max(n, 1)
        for j in range(max(0, int(centre - band)), min(m, int(centre + band)) + 1):
            if i == 0 and j == 0:
                continue
            best, how = INF, None
            for di, dj, pen in ((1, 1, 0.0), (1, 0, 3.0), (0, 1, 3.0), (1, 2, 1.0), (2, 1, 1.0)):
                pi, pj = i - di, j - dj
                if pi < 0 or pj < 0 or (pi, pj) not in cost:
                    continue
                c = cost[(pi, pj)] + pen
                if di and dj:
                    c += lc(sum(G[pi:i]), sum(E[pj:j]))
                    if di == 1 and dj == 1 and gk[pi] == ek[pj]:
                        c -= 0.6
                    elif dj == 1 and gk[pi] == ek[pj] or di == 1 and gk[pi] == ek[pj]:
                        c -= 0.3
                if c < best:
                    best, how = c, (di, dj)
            if how:
                cost[(i, j)] = best
                back[(i, j)] = how
    owner = [[] for _ in range(n)]
    i, j = n, m
    if (i, j) not in back:          # shouldn't happen; fall back to nothing
        return owner
    pending = []                    # English with no Greek: give it to the verse before
    while i > 0 or j > 0:
        di, dj = back[(i, j)]
        if di == 0:
            pending.extend(range(j - dj, j))
        else:
            target = i - 1                  # with two Greek verses, the English goes with the first
            owner[i - di].extend(range(j - dj, j))
            if pending:
                owner[target].extend(pending)
                pending = []
        i, j = i - di, j - dj
    if pending and owner:
        owner[0].extend(pending)
    return [sorted(o) for o in owner]


# Books whose LXX order differs from Brenton's numbering, so that the
# in-order alignment goes wrong in places (Proverbs 24–31, Sirach 30–36).
REORDERED = {"29.Proverbia", "34.Ecclesiasticus"}
STOP = set("""a an the and or but of to in on at by for with from as is are was were be been being it its
this that these those he she they them his her their him i me my we us our you your thou thee thy ye not no
shall will would should may might must do does did have has had which who whom what when where so than then
there here all also into upon unto out up""".split())


def stems(words):
    return {w[:5] for w in words if len(w) > 2 and w not in STOP}


def gloss_stems(text, glosses, lemma_of):
    out = set()
    for _st, _en, form in greek.tokenize(text):
        lemma = lemma_of.get(form)
        g = glosses.get(greek.lex_key(re.sub(r"\d+$", "", lemma))) if lemma else None
        if g:
            out |= stems(re.findall(r"[a-z]+", g.lower()))
    return out


def repair_order(greek_verses, english_verses, owner, glosses, lemma_of):
    """Move English verses that the in-order alignment put in the wrong place:
    each goes to the Greek verse whose glosses share most words with it,
    unless its current place is nearly as good."""
    G = [gloss_stems(t, glosses, lemma_of) for _, _, t in greek_verses]
    E = [stems(re.findall(r"[a-z]+", t.lower())) for _, _, t, _ in english_verses]

    def score(i, j):
        if not G[i] or not E[j]:
            return 0.0
        return len(G[i] & E[j]) / (len(G[i]) * len(E[j])) ** 0.5

    where = {j: i for i, js in enumerate(owner) for j in js}
    new = [[] for _ in owner]
    moved = 0
    for j in range(len(english_verses)):
        cur = where.get(j)
        best = max(range(len(G)), key=lambda i: score(i, j))
        if cur is None or (score(best, j) >= 0.3 and score(cur, j) < 0.5 * score(best, j)):
            new[best].append(j)
            moved += cur != best
        else:
            new[cur].append(j)
    return [sorted(o) for o in new], moved


SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def build_book(db, sort, n, book, swete_dir, brenton_dir, frequency, stats_all):
    stem, code, title = book
    verses = read_swete(f"{swete_dir}/data/{stem}.txt")
    english = []
    if code:
        found = glob.glob(f"{brenton_dir}/data/source/usfm/*-{code}englxxup.usfm")
        english = read_brenton(found[0]) if found else []
    owner = pair(verses, english) if english else [[] for _ in verses]
    moved = 0
    if english and stem in REORDERED:
        forms = sorted({f for _, _, t in verses for _a, _b, f in greek.tokenize(t)})
        found = morpheus.analyses(forms, "attic", frequency)
        lemma_of = {f: rows[0][0] for f, rows in found.items() if rows}
        owner, moved = repair_order(verses, english, owner, GLOSSES, lemma_of)
    poetic = english and sum(1 for e in english if e[3] == "q") > len(english) / 3

    wid = db.execute(
        "INSERT INTO work(sort,urn,author,title,kind,form,greek_urn,english_urn,translator,scope,parse_source,"
        "language,credit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sort, URN.format(int(stem[:2])), "Septuagint", title, "prose", "bible",
         URN.format(int(stem[:2])) + ".1st1K-grc1", "", "Brenton (updated)" if english else "",
         "complete", "morpheus", "grc", CREDIT)).lastrowid

    tokens, seq = [], 0
    previous_chapter = None
    for bi, ((c, v, text), mine) in enumerate(zip(verses, owner)):
        cite = f"{c}.{v}"
        parts = [english[j] for j in mine]
        if len(parts) == 1:
            en = parts[0][2]
        else:
            en = " ".join(f"{p[1].translate(SUPERSCRIPT)}\u2009{p[2]}" for p in parts)
        heading = None
        if c != previous_chapter:
            heading = f"Psalm {c}" if stem.endswith("Psalmi") else f"Chapter {c}"
        para = c != previous_chapter or any(p[3] == "p" for p in parts) or (poetic and bool(parts)) \
            or any(p[3] == "q" for p in parts)
        previous_chapter = c
        bid = db.execute("INSERT INTO block(work_id,seq,cite_start,cite_end,english,english_markers)"
                         " VALUES (?,?,?,?,?,?)", (wid, bi, cite, cite, en, "[]")).lastrowid
        sid = db.execute(
            "INSERT INTO segment(work_id,block_id,seq,cite,line_n,speaker,heading,part,para_start,text,markers)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (wid, bid, seq, cite, None, None, heading, None, 1 if para else 0, text,
             json.dumps([[0, "section", v]]))).lastrowid
        seq += 1
        for t in tokens_for(text, 0):
            t["seg"] = sid
            tokens.append(t)

    need = sorted({t["form"] for t in tokens})
    analyses = morpheus.analyses(need, "attic", frequency) if need else {}
    # Koine spellings: parse the Attic spelling instead
    missing = [f for f in need if not analyses.get(f)]
    variants = {f: koine_variants(f) for f in missing}
    extra = morpheus.analyses(sorted({v for vs in variants.values() for v in vs}), "attic", frequency) \
        if any(variants.values()) else {}
    for f, vs in variants.items():
        for v in vs:
            if extra.get(v):
                analyses[f] = extra[v]
                break
    stats = Counter()
    for t in tokens:
        found = analyses.get(t["form"]) or []
        source = "morpheus" if found else None
        lemma = found[0][0] if found else None
        if not found:
            # a proper name (mostly): the NT's lemma for the same form, or the form itself
            lemma = NT_FORMS.get(greek.bare(t["form"]))
            if lemma:
                stats["nt_form"] += 1
            elif t["form"][:1].isupper():
                lemma = t["form"]
                stats["name"] += 1
            else:
                stats["no_parse"] += 1
        else:
            stats["morpheus"] += 1
        db.execute('INSERT INTO token(segment_id,idx,start,"end",form,lemma,lemma_key,postag,source)'
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (t["seg"], t["idx"], t["start"], t["end"], t["form"], lemma,
                    greek.lex_key(re.sub(r"\d+$", "", lemma)) if lemma else None, None, source))
    for form, rows in analyses.items():
        for rank, (lemma, parse) in enumerate(rows):
            db.execute("INSERT INTO analysis VALUES (?,?,?,?,?)",
                       (form, rank, lemma, greek.lex_key(lemma), parse))
    stats_all.update(stats)
    matched = sum(1 for o in owner if o)
    return dict(verses=len(verses), with_english=matched, english_verses=len(english), tokens=len(tokens),
                english_moved=moved,
                names=stats["name"] + stats["nt_form"],
                unparsed=f"{100 * stats['no_parse'] / max(1, len(tokens)):.1f}%")


NT_FORMS = {}       # bare NT word form -> MACULA lemma (names above all)


def nt_frequency(macula_tsv):
    """Lemma counts in the NT (MACULA): Koine usage, to rank Morpheus's
    readings. Also fills NT_FORMS (form -> lemma) for names Morpheus lacks."""
    c = Counter()
    forms = defaultdict(Counter)
    if macula_tsv and os.path.exists(macula_tsv):
        with open(macula_tsv, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                lemma = re.sub(r"\((\w)\)$", r"\1", r["lemma"])
                c[greek.lex_key(lemma)] += 1
                forms[greek.bare(r["text"])][lemma] += 1
    NT_FORMS.update({f: l.most_common(1)[0][0] for f, l in forms.items()})
    return c


GLOSSES = {}        # lemma key -> Logeion short definition (for repair_order)


def main(swete_dir, brenton_dir, tbdir, out, macula_tsv=None, shortdefs=None):
    if shortdefs and os.path.exists(shortdefs):
        for line in open(shortdefs, encoding="utf-8"):
            k, _, d = line.rstrip("\n").partition("\t")
            if d:
                GLOSSES.setdefault(greek.lex_key(k), d)
    db = sqlite3.connect(out)
    cols = [r[1] for r in db.execute("PRAGMA table_info(work)")]
    for col in ("language", "credit"):
        if col not in cols:
            db.execute(f"ALTER TABLE work ADD COLUMN {col} TEXT")
    frequency = Counter(lemma_frequency(tbdir))
    frequency.update(nt_frequency(macula_tsv))
    start = db.execute("SELECT COALESCE(MAX(sort), 0) FROM work").fetchone()[0] + 1
    report, total = {}, Counter()
    for i, book in enumerate(BOOKS):
        report[book[2]] = build_book(db, start + i, i, book, swete_dir, brenton_dir, frequency, total)
    db.execute("DELETE FROM analysis WHERE rowid NOT IN (SELECT MIN(rowid) FROM analysis GROUP BY form, rank)")
    db.commit()
    report["total"] = dict(total, unparsed=f"{100 * total['no_parse'] / max(1, sum(total.values())):.2f}%")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:7])
