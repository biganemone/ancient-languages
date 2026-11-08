"""Export some works from the full texts database as a standalone module file.

  python export_module.py <texts_app.db> <out.db> [--urn URN ...] [--author NAME ...] [--language CODE ...]
                          [--defaults] [--within] [--deflate OUT.db.z]

The app ships one module (the default texts, --defaults) and downloads others
(make_modules.py); it copies a module's rows into its own library database
(claude/loading-texts-plan.md). Every module of one build keeps the full
build's row ids, which never collide between works, so no renumbering is
needed. The output has the app schema (compact_texts.SCHEMA) with only the
chosen works and what they refer to:

  - work, part, block, segment, token, morph rows of those works
    (tokens are numbered per work: work.token_first..token_last);
  - the lemma, tag and parse rows they use;
  - Morpheus analyses for the word forms that occur in them;
  - parallel-map rows whose either side is one of them (by URN), or, with
    --within, whose both sides are;
  - the build's `meta` table (stamp_build.py), so the app can refuse a module
    from another build.

Unique indexes on analysis(form, rank) and parallel let the app add modules
with INSERT OR IGNORE; auto_vacuum=INCREMENTAL lets it give space back when
texts are removed.
"""
import argparse
import os
import sqlite3
import zlib

import compact_texts

EXTRA_INDEXES = """
CREATE UNIQUE INDEX analysis_key ON analysis(form, rank);
CREATE UNIQUE INDEX parallel_key ON parallel(urn, cite, other_urn, other_cite);
CREATE INDEX parallel_urn ON parallel(urn);
CREATE INDEX block_cite ON block(work_id, cite_start);
"""


def chunks(ids, n=900):
    ids = list(ids)
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


def copy_rows(s, d, table, column, ids):
    cols = [r[1] for r in s.execute(f"PRAGMA table_info({table})")]
    marks = ",".join("?" * len(cols))
    for part in chunks(sorted(ids)):
        q = ",".join("?" * len(part))
        d.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({marks})",
                      s.execute(f"SELECT * FROM {table} WHERE {column} IN ({q})", part))


def select_works(s, urns=(), authors=(), languages=()):
    out = []
    for wid, urn, author, lang in s.execute("SELECT id, urn, author, COALESCE(NULLIF(language, ''), 'grc') FROM work"):
        if urn in urns or author in authors or lang in languages:
            out.append(wid)
    return out


def export(s, works, out, within=False):
    """Write the works (ids in the source connection `s`) to `out`; returns row counts."""
    if os.path.exists(out):
        os.remove(out)
    d = sqlite3.connect(out)
    d.execute("PRAGMA auto_vacuum = INCREMENTAL")          # must come before any table
    d.executescript(compact_texts.SCHEMA)
    d.execute("CREATE TABLE parallel (urn TEXT, cite TEXT, other_urn TEXT, other_cite TEXT)")
    d.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    d.executescript(EXTRA_INDEXES)
    if s.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone():
        d.executemany("INSERT INTO meta VALUES (?, ?)", s.execute("SELECT key, value FROM meta"))

    copy_rows(s, d, "work", "id", works)
    for table in ("part", "block", "segment"):
        copy_rows(s, d, table, "work_id", works)

    ranges = s.execute(f"SELECT token_first, token_last FROM work WHERE id IN ({','.join('?' * len(works))})",
                       works).fetchall() if works else []
    lemmas, tags, forms = set(), set(), set()
    texts = dict(d.execute("SELECT id, text FROM segment"))
    for first, last in ranges:
        if first is None:
            continue
        rows = s.execute("SELECT * FROM token WHERE id BETWEEN ? AND ?", (first, last)).fetchall()
        d.executemany(f"INSERT INTO token VALUES ({','.join('?' * len(rows[0]))})", rows) if rows else None
        for tid, seg, idx, start, length, lid, tag, source, word, form, aor in rows:
            lemmas.update(x for x in (lid, aor) if x)
            if tag:
                tags.add(tag)
            forms.add(form or compact_texts.u16_slice(texts[seg], start, start + length))
        morphs = s.execute("SELECT * FROM morph WHERE token_id BETWEEN ? AND ?", (first, last)).fetchall()
        d.executemany("INSERT INTO morph VALUES (?,?,?,?,?)", morphs)
        for _, _, _, lid, tag in morphs:
            if lid:
                lemmas.add(lid)
            if tag:
                tags.add(tag)

    # the Morpheus analyses of the forms that occur (looked up as written and lowercased)
    forms |= {f.lower() for f in forms}
    parses = set()
    for part in chunks(sorted(forms)):
        q = ",".join("?" * len(part))
        rows = s.execute(f"SELECT * FROM analysis WHERE form IN ({q})", part).fetchall()
        d.executemany("INSERT OR IGNORE INTO analysis VALUES (?,?,?,?)", rows)
        for _, _, lid, pid in rows:
            lemmas.add(lid)
            parses.add(pid)
    # an aorist's lemma row points at its verb
    lemmas |= {b for (b,) in s.execute(
        f"SELECT base_id FROM lemma WHERE kind = 1 AND id IN ({','.join(map(str, lemmas)) or 'NULL'})") if b}
    copy_rows(s, d, "lemma", "id", lemmas)
    copy_rows(s, d, "tag", "id", tags)
    copy_rows(s, d, "parse", "id", parses)

    urns = [u for (u,) in d.execute("SELECT urn FROM work")]
    installed = set(urns)
    for part in chunks(urns):
        q = ",".join("?" * len(part))
        rows = s.execute(f"SELECT * FROM parallel WHERE urn IN ({q}) OR other_urn IN ({q})", part + part)
        if within:                         # both sides in this module
            rows = [r for r in rows if r[0] in installed and r[2] in installed]
        d.executemany("INSERT OR IGNORE INTO parallel VALUES (?,?,?,?)", rows)

    d.executescript(compact_texts.INDEXES)
    d.commit()
    d.execute("VACUUM")
    counts = {t: d.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("work", "segment", "token", "lemma", "analysis", "parallel")}
    d.close()
    return counts


def deflate(src, dst, level=9):
    """Raw DEFLATE (Apple's COMPRESSION_ZLIB), streamed; the app inflates it with the Compression framework."""
    c = zlib.compressobj(level, zlib.DEFLATED, -15)
    with open(src, "rb") as f, open(dst, "wb") as g:
        while True:
            block = f.read(1 << 20)
            if not block:
                break
            g.write(c.compress(block))
        g.write(c.flush())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("out")
    ap.add_argument("--urn", action="append", default=[])
    ap.add_argument("--author", action="append", default=[])
    ap.add_argument("--language", action="append", default=[], help="lat, cop, or grc (no language set)")
    ap.add_argument("--defaults", action="store_true", help="the works the app ships with (defaults.py)")
    ap.add_argument("--within", action="store_true",
                    help="keep only parallel links between exported works (implied by --defaults)")
    ap.add_argument("--deflate", help="also write a raw-DEFLATE copy here (what the app bundles)")
    a = ap.parse_args()
    if a.defaults:
        import defaults
        a.urn += defaults.URNS
        a.author += defaults.AUTHORS
        a.language += defaults.LANGUAGES
        a.within = True
    s = sqlite3.connect(a.db)
    works = select_works(s, a.urn, a.author, a.language)
    counts = export(s, works, a.out, a.within)
    print(f"{a.out}: {os.path.getsize(a.out) / 1e6:.1f} MB", counts)
    if a.deflate:
        deflate(a.out, a.deflate)
        print(f"{a.deflate}: {os.path.getsize(a.deflate) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
