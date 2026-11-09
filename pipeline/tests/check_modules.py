"""Check that modules add to and remove from a library database the way the
app does it (Data/LibraryDatabase.swift), using the same SQL.

  python tests/check_modules.py <texts.db.z (shipped)> <modules dir> <urn to add> <urn to remove>
"""
import os
import sqlite3
import sys
import tempfile
import zlib


def inflate(src, dst):
    d = zlib.decompressobj(-15)
    with open(src, "rb") as f, open(dst, "wb") as g:
        for block in iter(lambda: f.read(1 << 20), b""):
            g.write(d.decompress(block))
        g.write(d.flush())


def copy_works(lib, module):
    db = sqlite3.connect(lib, isolation_level=None)
    db.execute("ATTACH DATABASE ? AS m", (module,))
    assert db.execute("SELECT value FROM m.meta WHERE key='build'").fetchone() == \
        db.execute("SELECT value FROM main.meta WHERE key='build'").fetchone(), "build mismatch"
    works = db.execute("SELECT id, urn, token_first, token_last FROM m.work "
                       "WHERE urn NOT IN (SELECT urn FROM main.work)").fetchall()
    db.execute("BEGIN")
    for wid, urn, first, last in works:
        db.execute("INSERT OR IGNORE INTO main.work SELECT * FROM m.work WHERE id = ?", (wid,))
        for t in ("part", "block", "segment"):
            db.execute(f"INSERT OR IGNORE INTO main.{t} SELECT * FROM m.{t} WHERE work_id = ?", (wid,))
        if first is not None:
            db.execute("INSERT OR IGNORE INTO main.token SELECT * FROM m.token WHERE id BETWEEN ? AND ?", (first, last))
            db.execute("INSERT INTO main.morph SELECT * FROM m.morph WHERE token_id BETWEEN ? AND ?", (first, last))
        db.execute("INSERT OR IGNORE INTO main.parallel SELECT * FROM m.parallel WHERE urn = ? OR other_urn = ?",
                   (urn, urn))
    for t in ("lemma", "tag", "parse", "analysis"):
        db.execute(f"INSERT OR IGNORE INTO main.{t} SELECT * FROM m.{t}")
    db.execute("COMMIT")
    return [w[1] for w in works]


def remove_works(lib, urns):
    db = sqlite3.connect(lib, isolation_level=None)
    db.execute("BEGIN")
    for urn in urns:
        for wid, first, last in db.execute("SELECT id, token_first, token_last FROM work WHERE urn = ?",
                                           (urn,)).fetchall():
            if first is not None:
                db.execute("DELETE FROM morph WHERE token_id BETWEEN ? AND ?", (first, last))
                db.execute("DELETE FROM token WHERE id BETWEEN ? AND ?", (first, last))
            for t in ("segment", "block", "part"):
                db.execute(f"DELETE FROM {t} WHERE work_id = ?", (wid,))
            db.execute("DELETE FROM work WHERE id = ?", (wid,))
    db.execute("COMMIT")
    db.execute("PRAGMA incremental_vacuum").fetchall()


def counts(lib, urn):
    db = sqlite3.connect(lib)
    r = db.execute("SELECT id, token_first, token_last FROM work WHERE urn = ?", (urn,)).fetchone()
    if not r:
        return None
    wid, a, b = r
    return dict(segments=db.execute("SELECT COUNT(*) FROM segment WHERE work_id=?", (wid,)).fetchone()[0],
                tokens=db.execute("SELECT COUNT(*) FROM token WHERE id BETWEEN ? AND ?", (a, b)).fetchone()[0])


def main(bundle, modules, add, remove):
    import json
    tmp = tempfile.mkdtemp()
    lib = os.path.join(tmp, "library.db")
    inflate(bundle, lib)
    print("library", os.path.getsize(lib) // 1_000_000, "MB; auto_vacuum",
          sqlite3.connect(lib).execute("PRAGMA auto_vacuum").fetchone()[0])
    manifest = json.load(open(os.path.join(modules, "modules.json")))
    mod = os.path.join(tmp, "m.db")
    inflate(os.path.join(modules, manifest["modules"][add]["file"]), mod)
    print("added", copy_works(lib, mod), counts(lib, add))
    print("again (should add nothing)", copy_works(lib, mod))
    print("before removal", counts(lib, remove), os.path.getsize(lib) // 1_000_000, "MB")
    remove_works(lib, [remove])
    print("after removal", counts(lib, remove), os.path.getsize(lib) // 1_000_000, "MB")
    db = sqlite3.connect(lib)
    print("integrity", db.execute("PRAGMA integrity_check").fetchone()[0])
    # the removed text, added back from the full-build module, matches the module
    inflate(os.path.join(modules, manifest["modules"][remove]["file"]), mod)
    print("re-added", copy_works(lib, mod), counts(lib, remove))


if __name__ == "__main__":
    main(*sys.argv[1:5])
