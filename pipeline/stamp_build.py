"""Stamp the full texts database with a build id (claude/loading-texts-plan.md).

  python stamp_build.py <texts_app.db>

The id ("20261107T2015Z") goes in a `meta` table; export_module.py copies it
into the shipped database and every module, and make_catalog.py into
catalog.json. The app only adds a module whose build matches its library's,
because row ids are only consistent within one build."""
import sqlite3
import sys
from datetime import datetime, timezone


def main(path):
    build = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT OR REPLACE INTO meta VALUES ('build', ?)", (build,))
    db.commit()
    print(f"{path}: build {build}")


if __name__ == "__main__":
    main(sys.argv[1])
