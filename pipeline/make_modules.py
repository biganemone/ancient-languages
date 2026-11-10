"""Cut a downloadable module for every work in the full build.

  python make_modules.py <texts_app.db (full)> <modules dir> [--max-seconds N]

Each work becomes <dir>/<id>.db.z (export_module.py, raw DEFLATE), listed in
<dir>/modules.json with its size and SHA-256; make_catalog.py copies those
into catalog.json. One module per work keeps choices fine-grained ("Add all"
in the app adds a group). Re-running skips modules already made for this
build, so the job can be split (--max-seconds) across short runs."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import time

from export_module import deflate, export


def module_id(urn):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", urn.replace("urn:", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("dir")
    ap.add_argument("--max-seconds", type=float, default=0)
    ap.add_argument("--dictionary", action="append", default=[], metavar="LANG=PATH",
                    help="a downloadable dictionary (lexicon file of the same build), e.g. non=build/lexicon_non.db")
    a = ap.parse_args()
    start = time.time()
    os.makedirs(a.dir, exist_ok=True)
    s = sqlite3.connect(a.db)
    build = s.execute("SELECT value FROM meta WHERE key = 'build'").fetchone()[0]
    manifest_path = os.path.join(a.dir, "modules.json")
    manifest = {"build": build, "modules": {}}
    if os.path.exists(manifest_path):
        old = json.load(open(manifest_path))
        if old.get("build") == build:
            manifest = old
    works = s.execute("SELECT id, urn FROM work ORDER BY sort").fetchall()
    made = 0
    for wid, urn in works:
        m = manifest["modules"].get(urn)
        if m and os.path.exists(os.path.join(a.dir, m["file"])):
            continue
        if a.max_seconds and time.time() - start > a.max_seconds:
            break
        name = module_id(urn)
        tmp = os.path.join(a.dir, name + ".db")
        export(s, [wid], tmp)
        z = os.path.join(a.dir, name + ".db.z")
        deflate(tmp, z)
        os.remove(tmp)
        digest = hashlib.sha256(open(z, "rb").read()).hexdigest()
        manifest["modules"][urn] = {"file": name + ".db.z", "bytes": os.path.getsize(z), "sha256": digest}
        made += 1
        json.dump(manifest, open(manifest_path, "w"), indent=0)
    # dictionary modules: the lexicon file itself, deflated (dict-<lang>.db.z)
    for spec in a.dictionary:
        lang, path = spec.split("=", 1)
        lx = sqlite3.connect(path)
        lbuild = lx.execute("SELECT value FROM meta WHERE key = 'build'").fetchone()[0]
        if lbuild != build:
            raise SystemExit(f"{path} is build {lbuild}, the texts {build}: stamp them together (stamp_build.py)")
        titles = lx.execute("SELECT id, title FROM dictionary ORDER BY rowid").fetchall()
        lx.close()
        name = f"dict-{lang}.db.z"
        z = os.path.join(a.dir, name)
        deflate(path, z)
        digest = hashlib.sha256(open(z, "rb").read()).hexdigest()
        manifest.setdefault("dictionaries", {})[lang] = {
            "file": name, "bytes": os.path.getsize(z), "sha256": digest,
            "dictionaries": [{"id": i, "title": t} for i, t in titles]}
        json.dump(manifest, open(manifest_path, "w"), indent=0)
        print(f"{z}: {os.path.getsize(z) / 1e6:.1f} MB, {len(titles)} dictionaries")
    done = sum(1 for _, u in works if u in manifest["modules"])
    print(f"{a.dir}: made {made}, {done}/{len(works)} done for build {build}")


if __name__ == "__main__":
    main()
