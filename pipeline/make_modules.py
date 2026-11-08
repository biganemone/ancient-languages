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
    done = sum(1 for _, u in works if u in manifest["modules"])
    print(f"{a.dir}: made {made}, {done}/{len(works)} done for build {build}")


if __name__ == "__main__":
    main()
