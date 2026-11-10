#!/usr/bin/env bash
# Publish this build's text modules as a GitHub Release, which the app
# downloads from (claude/loading-texts-plan.md). Run after build.sh, before
# building the app; needs the GitHub CLI, signed in (brew install gh; gh auth login).
#
#   pipeline/publish_release.sh            create the release, or finish an interrupted upload
#   pipeline/publish_release.sh --check    only check the files, upload nothing
#
# The tag is texts-<build>. Releases are never replaced: a new build gets a new
# release, and older app versions keep downloading from theirs.
set -euo pipefail
cd "$(dirname "$0")"

REPO=biganemone/ancient-languages
catalog=../app/AncientLanguages/Resources/Databases/catalog.json
modules=build/modules
check_only=${1:-}

build=$(python3 -c "import json; print(json.load(open('$catalog'))['build'])")
tag="texts-$build"
expected="https://github.com/$REPO/releases/download/$tag"

# 1. the files match the catalog the app will ship with
python3 - "$catalog" "$modules" "$expected" <<'EOF'
import hashlib, json, os, sys
catalog, modules, expected = sys.argv[1:4]
c = json.load(open(catalog))
m = json.load(open(os.path.join(modules, "modules.json")))
problems = []
if c.get("downloads") != expected:
    problems.append(f"catalog.json downloads is {c.get('downloads')!r}, expected {expected!r} (re-run make_catalog.py)")
if m.get("build") != c["build"]:
    problems.append(f"modules.json is build {m.get('build')}, catalog.json {c['build']}")
for w in c["works"]:
    path = os.path.join(modules, w["module"] or "")
    if not w["module"] or not os.path.exists(path):
        problems.append(f"no module for {w['urn']}")
    elif hashlib.sha256(open(path, "rb").read()).hexdigest() != w["sha256"]:
        problems.append(f"checksum differs for {w['module']}")
for d in c.get("dictionaries", []):
    path = os.path.join(modules, d["module"])
    if not os.path.exists(path):
        problems.append(f"no dictionary module {d['module']}")
    elif hashlib.sha256(open(path, "rb").read()).hexdigest() != d["sha256"]:
        problems.append(f"checksum differs for {d['module']}")
for p in problems[:20]:
    print("  ", p)
if problems:
    sys.exit(f"{len(problems)} problem(s); nothing published")
print(f"{len(c['works'])} modules match catalog.json (build {c['build']})")
EOF
[ "$check_only" = "--check" ] && exit 0

command -v gh >/dev/null || { echo "Install the GitHub CLI first: brew install gh; gh auth login"; exit 1; }

notes=build/release_notes.md
credits=build/CREDITS.md
python3 release_notes.py "$catalog" "$notes" "$credits"
cp "$catalog" build/catalog.json

# 2. create the release (once), then upload whatever isn't there yet
if ! gh release view "$tag" --repo "$REPO" >/dev/null 2>&1; then
  gh release create "$tag" --repo "$REPO" --title "Texts $build" --notes-file "$notes" --latest=false \
    build/catalog.json "$modules/modules.json" "$credits"
fi
have=$(gh release view "$tag" --repo "$REPO" --json assets --jq '.assets[].name')
todo=()
for f in "$modules"/*.db.z; do
  grep -qxF "$(basename "$f")" <<<"$have" || todo+=("$f")
done
echo "${#todo[@]} module(s) to upload"
# in batches, so an interruption loses little; re-run to finish
for ((i = 0; i < ${#todo[@]}; i += 25)); do
  gh release upload "$tag" --repo "$REPO" "${todo[@]:i:25}"
  done_n=$((i + 25)); [ $done_n -gt ${#todo[@]} ] && done_n=${#todo[@]}
  echo "  uploaded $done_n/${#todo[@]}"
done

# 3. check: every module is there, and one downloads with the right checksum
count=$(gh release view "$tag" --repo "$REPO" --json assets --jq '[.assets[].name | select(endswith(".db.z"))] | length')
echo "release $tag has $count modules"
sample=$(python3 -c "import json; w=json.load(open('$catalog'))['works']; w=[x for x in w if not x['bundled']][0]; print(w['module'], w['sha256'])")
set -- $sample
got=$(curl -sL "$expected/$1" | shasum -a 256 | cut -d' ' -f1)
[ "$got" = "$2" ] && echo "download check OK ($1)" || { echo "download check FAILED for $1"; exit 1; }
echo "Published: https://github.com/$REPO/releases/tag/$tag"
