"""Write the catalog of every text the project offers (the full build's
works), which the app uses for "Add Texts" and to install or re-install texts.

  python make_catalog.py <texts_app.db (full)> <shipped texts.db> <modules dir> <catalog.json> [downloads URL]

Each entry: urn, language, author (or group), title, translator, scope, word
count, whether it ships in the app (`bundled`), and its module (file, bytes,
sha256) from make_modules.py. `build` is the full build's id; `downloads` is
the URL the module files are served from (a GitHub Release,
publish_release.sh); "{build}" in it is replaced by the build id, e.g.
https://github.com/biganemone/ancient-languages/releases/download/texts-{build}"""
import json
import os
import sqlite3
import sys


def main(db_path, shipped_path, modules_dir, out, downloads=""):
    db = sqlite3.connect(db_path)
    build = db.execute("SELECT value FROM meta WHERE key = 'build'").fetchone()[0]
    downloads = (downloads or "").replace("{build}", build).rstrip("/")
    shipped = {u for (u,) in sqlite3.connect(shipped_path).execute("SELECT urn FROM work")}
    manifest = {}
    mpath = os.path.join(modules_dir, "modules.json")
    if os.path.exists(mpath):
        m = json.load(open(mpath))
        if m.get("build") == build:
            manifest = m["modules"]
    works = []
    for urn, lang, author, title, translator, scope, first, last in db.execute(
            "SELECT urn, COALESCE(NULLIF(language, ''), 'grc'), author, title, translator, scope, token_first, "
            "token_last FROM work ORDER BY sort"):
        words = (last - first + 1) if first is not None and last is not None else 0
        mod = manifest.get(urn, {})
        works.append(dict(urn=urn, language=lang, author=author, title=title, translator=translator or "",
                          scope=scope or "complete", words=words, bundled=urn in shipped,
                          module=mod.get("file"), bytes=mod.get("bytes"), sha256=mod.get("sha256")))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(version=2, build=build, downloads=downloads, works=works), f, ensure_ascii=False, indent=0)
    print(f"{out}: {len(works)} works, {sum(1 for w in works if w['module'])} with modules, build {build}",
          f"downloads {downloads}" if downloads else "(no downloads URL)")


if __name__ == "__main__":
    main(*sys.argv[1:6])
