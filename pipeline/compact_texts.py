"""Rewrite texts.db into the compact form the app ships.

Usage: python compact_texts.py <texts.db from the builders> <out.db> [lexicon.db]

The builders write a roomy schema that is easy to inspect and that
build_lexicon.py reads. For the app, the token table (over a million rows)
dominates the file, so:

  - a token's written form is not stored: it is the segment text between
    `start` and `start + len`. (Only where the shown form differs from that
    slice, a Coptic word broken across two lines, is `form` kept.)
  - lemmas (with their lookup keys), part-of-speech tags and Morpheus parse
    descriptions are stored once, in their own tables, and referred to by id;
  - `source` is a small integer (see SOURCES);
  - tokens are numbered in reading order within each work, and the work
    records its first and last token id, so the app reads a work's tokens
    as one id range and the segment index on the token table is dropped.

It also adds what flashcards need (see claude/flashcards-plan.md):

  - lemma.gloss: the short definition (from lexicon.db, when given);
  - lemma.function: 1 for function words (articles, particles,
    conjunctions, prepositions, pronouns; in Coptic, everything but nouns,
    verbs, adverbs and numerals), skipped by default;
  - second and irregular aorists as entries of their own: a lemma row with
    kind = 1, its headword the aorist (εἶπον), base_id pointing to the verb
    (λέγω); tokens of such aorists carry aor_id;
  - part: each part's token range (books, hymns, codex pages), for decks
    drawn from a range of books.

Nothing the user keeps (notes, highlights, bookmarks, reading positions,
decks) refers to row ids, which change with every build: they use work URNs,
citations, offsets and lemma keys. The parallel map is stored the same way.
"""
import gzip
import unicodedata
from collections import Counter, defaultdict

import aorists
import greek
import sqlite3
import sys

SOURCES = {None: 0, "morpheus": 1, "treebank": 2, "scriptorium": 3, "coptic-nlp": 4, "oe-forms": 5, "oshb": 6, "dcs": 7, "non-forms": 8}

SCHEMA = """
CREATE TABLE work (
  id INTEGER PRIMARY KEY, sort INT, urn TEXT, author TEXT, title TEXT, kind TEXT, form TEXT,
  greek_urn TEXT, english_urn TEXT, translator TEXT, scope TEXT, parse_source TEXT,
  language TEXT, credit TEXT, token_first INT, token_last INT);
CREATE TABLE block (
  id INTEGER PRIMARY KEY, work_id INT, seq INT, cite_start TEXT, cite_end TEXT, english TEXT);
CREATE TABLE segment (
  id INTEGER PRIMARY KEY, work_id INT, block_id INT, seq INT, cite TEXT,
  line_n INT, speaker TEXT, heading TEXT, part TEXT, para_start INT, text TEXT, markers TEXT);
-- kind: 0 a dictionary word, 1 a second/irregular aorist (base_id: its verb)
CREATE TABLE lemma (id INTEGER PRIMARY KEY, lemma TEXT, key TEXT, gloss TEXT, function INT DEFAULT 0,
                    kind INT DEFAULT 0, base_id INT);
CREATE TABLE part (work_id INT, seq INT, key TEXT, token_first INT, token_last INT);
CREATE TABLE tag (id INTEGER PRIMARY KEY, tag TEXT);
CREATE TABLE parse (id INTEGER PRIMARY KEY, parse TEXT);
-- start/len: UTF-16 units into segment.text; source: 0 none, 1 Morpheus,
-- 2 treebank, 3 Coptic SCRIPTORIUM, 4 Coptic NLP (automatic), 5 Old English form tables (oe_forms.py), 6 Open Scriptures Hebrew Bible,
-- 8 Old Norse form tables (non_forms.py)
CREATE TABLE token (
  id INTEGER PRIMARY KEY, segment_id INT, idx INT, start INT, len INT,
  lemma_id INT, tag_id INT, source INT, word_id INT, form TEXT, aor_id INT);
CREATE TABLE morph (token_id INT, rank INT, form TEXT, lemma_id INT, tag_id INT);
CREATE TABLE analysis (form TEXT, rank INT, lemma_id INT, parse_id INT);
"""

INDEXES = """
CREATE INDEX seg_work ON segment(work_id, seq);
CREATE INDEX block_work ON block(work_id, seq);
CREATE INDEX morph_token ON morph(token_id);
CREATE INDEX analysis_form ON analysis(form);
"""


def u16_slice(text, start, end):
    b = text.encode("utf-16-le")
    return b[2 * start:2 * end].decode("utf-16-le", errors="replace")


class Interner:
    def __init__(self, db, table, columns):
        self.db, self.table, self.columns, self.ids = db, table, columns, {}

    def __call__(self, *values):
        if all(v is None for v in values):
            return None
        if values not in self.ids:
            marks = ",".join("?" * len(values))
            self.ids[values] = self.db.execute(
                f"INSERT INTO {self.table}({','.join(self.columns)}) VALUES ({marks})", values).lastrowid
        return self.ids[values]


FUNCTION_POS = {"l", "g", "c", "r", "p"}       # AGDT: article, particle, conjunction, preposition, pronoun
COPTIC_CONTENT = {"N", "NPROP", "V", "VBD", "VSTAT", "VIMP", "ADV", "NUM"}
# Coptic SCRIPTORIUM tag -> the part of speech the Comprehensive Coptic Lexicon gives
COPTIC_POS = {"N": "noun", "NPROP": "noun", "V": "verb", "VBD": "verb", "VSTAT": "verb", "VIMP": "verb",
              "ADV": "adverb", "PREP": "preposition", "CONJ": "conjunction", "PTC": "particle", "NUM": "numeral"}
FUNCTION_HEADS = {"article", "particle", "conjunction", "preposition", "pronoun"}   # Morpheus parse heads


def aorist_rank(postag, parse):
    """How well a form serves as an aorist's headword: 1st sg indicative
    active, then middle, then any indicative, then anything."""
    if postag:
        p = (postag + "---------")[:9]
        if p[4] == "i" and p[1] == "1" and p[2] == "s":
            return 0 if p[5] == "a" else 1
        return 2 if p[4] == "i" else 3
    parse = parse or ""
    if "indicative" in parse and "1st person" in parse and "singular" in parse:
        return 0 if "active" in parse else 1
    return 2 if "indicative" in parse else 3


def headword(form):
    form = form.rstrip(greek.ELISION)
    return unicodedata.normalize("NFC", form[:1].lower() + form[1:])


def word_facts(s):
    """Per lemma key: function-word share and second-aorist headwords, from
    all tokens of all works. -> (function keys, {token id: base key}, {base key: headword})"""
    parse0 = {form: (key, parse) for form, key, parse in
              s.execute("SELECT form, lemma_key, parse FROM analysis WHERE rank = 0")}
    # headwords come from Attic texts where possible (ἔλαβον, not Homer's unaugmented λάβον)
    from works import WORKS
    epic_urns = {f"urn:cts:greekLit:{w['work']}" for w in WORKS if w.get("dialect") != "attic"}
    epic_segments = {sid for sid, urn in s.execute(
        "SELECT g.id, w.urn FROM segment g JOIN work w ON w.id = g.work_id") if urn in epic_urns}
    stems = aorists.load()
    function_n, total = Counter(), Counter()
    coptic_pos = defaultdict(Counter)          # Coptic lemma -> its tags, to pick the right homograph
    aorist_tokens, candidates = {}, defaultdict(Counter)
    for tid, form, key, postag, source, seg in s.execute(
            "SELECT id, form, lemma_key, postag, source, segment_id FROM token WHERE lemma_key IS NOT NULL"):
        total[key] += 1
        if source in ("scriptorium", "coptic-nlp"):
            if postag not in COPTIC_CONTENT:
                function_n[key] += 1
            coptic_pos[key][postag] += 1
            continue
        # Morpheus's reading counts only if it is the reading the token was given
        parse = None
        if source == "morpheus" and parse0.get(form, (None,))[0] == key:
            parse = parse0[form][1]
        head = (parse or "").split(" · ")[0]
        if (postag and postag[0] in FUNCTION_POS) or head in FUNCTION_HEADS:
            function_n[key] += 1
        is_aorist = (postag[0] == "v" and len(postag) > 3 and postag[3] == "a") if postag \
            else (parse is not None and head in ("verb", "participle") and "aorist" in parse)
        if is_aorist and aorists.irregular([st for _, st in stems.get(greek.to_beta(form), [])]):
            aorist_tokens[tid] = key
            if len(greek.bare(form)) >= 3:    # (ἕν is "one", whatever Morpheus says)
                elided = form[-1:] in greek.ELISION
                candidates[key][(seg in epic_segments, elided, aorist_rank(postag, parse), headword(form))] += 1
    function = {k for k in total if function_n[k] * 2 >= total[k]}
    heads = {}
    for key, c in candidates.items():
        if sum(c.values()) >= 0.8 * total[key]:   # the lemma is itself an aorist (εἶπον, εἶδον)
            continue
        (_, _, _, form), _ = min(c.items(), key=lambda kv: (kv[0][:3], -kv[1]))
        if greek.lex_key(form) != key:          # εἶπον analysed as its own lemma needs no second card
            heads[key] = form
    pos = {k: COPTIC_POS.get(c.most_common(1)[0][0]) for k, c in coptic_pos.items()}
    return function, aorist_tokens, heads, pos


def glosses(lexicon_db, coptic_pos):
    """Short definition per lemma key. A Coptic key can have several (ϣⲁϫⲉ the
    noun and the verb); take the one whose part of speech matches how the
    word is tagged in the texts."""
    if not lexicon_db:
        return {}
    lx = sqlite3.connect(lexicon_db)
    found = defaultdict(list)
    for key, gloss, p, headword in lx.execute(
            "SELECT r.lemma_key, s.def, s.pos, s.lemma FROM resolve r JOIN shortdef s "
            "ON s.rowid = r.target WHERE r.dict = 'short' ORDER BY r.rowid"):
        found[key].append((gloss, p, headword == key))
    out = {}
    for key, options in found.items():
        if len(options) == 1 or key not in coptic_pos:
            out[key] = options[0][0]
            continue
        # Coptic homographs: the headword spelled exactly so (ϣⲱⲡⲉ, not ϣⲱⲡ ⲉ-), of the part of
        # speech the texts give it, without a query mark; then the gloss the lexicon repeats most
        wanted = coptic_pos[key]
        repeats = Counter(g for g, _, _ in options)
        best = sorted(options, key=lambda o: (not o[2], not (wanted and o[1] == wanted),
                                              o[0].rstrip().endswith("?"), -repeats[o[0]]))
        out[key] = best[0][0]
    return out


def main(src, out, lexicon_db=None, lexicon_extra=None):
    s = sqlite3.connect(src)
    d = sqlite3.connect(out)
    d.executescript(SCHEMA)
    lemma = Interner(d, "lemma", ["lemma", "key"])
    function, aorist_tokens, aorist_heads, coptic_pos = word_facts(s)
    gloss = glosses(lexicon_db, coptic_pos)
    if lexicon_extra:                       # the downloadable dictionaries (Old Norse's lexicon_non.db)
        gloss.update(glosses(lexicon_extra, coptic_pos))
    aorist_ids = {}
    tag = Interner(d, "tag", ["tag"])
    parse = Interner(d, "parse", ["parse"])

    cols = [r[1] for r in s.execute("PRAGMA table_info(work)")]
    has = lambda c: c in cols
    for row in s.execute("SELECT id, sort, urn, author, title, kind, form, greek_urn, english_urn, translator, "
                         f"scope, parse_source, {'language' if has('language') else 'NULL'}, "
                         f"{'credit' if has('credit') else 'NULL'} FROM work ORDER BY sort"):
        d.execute("INSERT INTO work VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)", row)
    d.executemany("INSERT INTO block VALUES (?,?,?,?,?,?)",
                  s.execute("SELECT id, work_id, seq, cite_start, cite_end, english FROM block"))
    d.executemany("INSERT INTO segment VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  s.execute("SELECT id, work_id, block_id, seq, cite, line_n, speaker, heading, part, "
                            "para_start, text, markers FROM segment"))

    # every work names its language (older builds left the Septuagint and NT NULL)
    d.execute("UPDATE work SET language = 'grc' WHERE language IS NULL OR language = ''")

    # tokens, renumbered in reading order work by work
    texts = dict(s.execute("SELECT id, text FROM segment"))
    new_id = {}
    next_id = 1
    for (wid,) in s.execute("SELECT id FROM work ORDER BY sort").fetchall():
        first = next_id
        rows = s.execute(
            'SELECT t.id, t.segment_id, t.idx, t.start, t."end", t.form, t.lemma, t.lemma_key, t.postag, '
            "t.source, t.word_id FROM token t JOIN segment g ON g.id = t.segment_id "
            "WHERE g.work_id = ? ORDER BY g.seq, t.idx", (wid,)).fetchall()
        for old, seg, idx, start, end, form, lem, key, postag, source, word in rows:
            shown = form if form != u16_slice(texts[seg], start, end) else None
            lid = lemma(lem, key) if lem else None
            aor = None
            base = aorist_tokens.get(old)
            if base in aorist_heads and lid:
                if base not in aorist_ids:
                    aorist_ids[base] = d.execute(
                        "INSERT INTO lemma(lemma, key, kind, base_id) VALUES (?,?,1,?)",
                        (aorist_heads[base], base + "|aor", lid)).lastrowid
                aor = aorist_ids[base]
            d.execute("INSERT INTO token VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (next_id, seg, idx, start, end - start, lid,
                       tag(postag) if postag else None, SOURCES[source], word, shown, aor))
            new_id[old] = next_id
            next_id += 1
        d.execute("UPDATE work SET token_first = ?, token_last = ? WHERE id = ?",
                  (first, next_id - 1, wid))
        # parts: books, hymns, codex pages ("2.123" -> "2"); one unnamed part otherwise
        cites = dict(s.execute("SELECT id, cite FROM segment WHERE work_id = ?", (wid,)))
        part_ranges = []
        for i, row in enumerate(rows):
            cite = cites[row[1]]
            key = cite.split(".")[0] if "." in cite else ""
            if not part_ranges or part_ranges[-1][0] != key:
                part_ranges.append([key, first + i, first + i])
            part_ranges[-1][2] = first + i
        d.executemany("INSERT INTO part VALUES (?,?,?,?,?)",
                      [(wid, n, k, a, b) for n, (k, a, b) in enumerate(part_ranges)])

    for token_id, rank, form, lem, key, pos in s.execute(
            "SELECT token_id, rank, form, lemma, lemma_key, pos FROM morph ORDER BY token_id, rank"):
        d.execute("INSERT INTO morph VALUES (?,?,?,?,?)",
                  (new_id[token_id], rank, form, lemma(lem, key) if lem else None, tag(pos) if pos else None))
    for form, rank, lem, key, p in s.execute("SELECT form, rank, lemma, lemma_key, parse FROM analysis"):
        d.execute("INSERT INTO analysis VALUES (?,?,?,?)", (form, rank, lemma(lem, key), parse(p)))

    # glosses and function-word flags; an aorist's gloss is its verb's
    for lid, key, base in d.execute("SELECT id, key, base_id FROM lemma").fetchall():
        if base:
            d.execute("UPDATE lemma SET gloss = ? WHERE id = ?",
                      (gloss.get(key.split("|")[0]), lid))
        else:
            d.execute("UPDATE lemma SET gloss = ?, function = ? WHERE id = ?",
                      (gloss.get(key), int(key in function), lid))

    # the parallel-text verse map (Vulgate <-> LXX / NT, Sahidic <-> NT), by
    # work URN and citation rather than block id, so that either side can be
    # installed (or rebuilt) on its own: a pair whose other work is missing
    # simply finds no block
    d.execute("CREATE TABLE parallel (urn TEXT, cite TEXT, other_urn TEXT, other_cite TEXT)")
    if s.execute("SELECT 1 FROM sqlite_master WHERE name = 'parallel'").fetchone():
        d.executemany("INSERT INTO parallel VALUES (?,?,?,?)", s.execute(
            "SELECT w.urn, b.cite_start, ow.urn, o.cite_start FROM parallel p "
            "JOIN block b ON b.id = p.block_id JOIN work w ON w.id = b.work_id "
            "JOIN block o ON o.id = p.other_block_id JOIN work ow ON ow.id = o.work_id "
            "ORDER BY w.sort, b.seq, ow.sort, o.seq"))
    d.execute("CREATE INDEX parallel_urn ON parallel(urn)")
    d.execute("CREATE INDEX block_cite ON block(work_id, cite_start)")

    d.executescript(INDEXES)
    d.commit()
    d.execute("VACUUM")
    d.close()


if __name__ == "__main__":
    main(*sys.argv[1:5])
