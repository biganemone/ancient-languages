#!/usr/bin/env bash
# Build the app's databases from Perseus / Logeion / Coptic sources.
#   pipeline/build.sh            fetch sources (first run only) and build
# Output: app/AncientLanguages/Resources/Databases/{texts,lexicon}.db (git-ignored)
#
# Parses for works without treebank data come from Morpheus. Its results are
# cached in pipeline/data/morpheus_cache.tsv.gz (committed), so Morpheus is
# only needed when works.py gains new texts: set MORPHEUS to a built checkout
# of https://github.com/perseids-tools/morpheus (see README).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
./fetch_sources.sh
out="$here/../app/AncientLanguages/Resources/Databases"
mkdir -p "$out" build
rm -f build/texts.db build/lexicon.db
python3 build_texts.py sources/canonical-greekLit/data sources/treebank_data/v2.1/Greek/texts build/texts.db \
  > build/texts_report.json
# the Septuagint (Swete + Morpheus + Updated Brenton), then the Greek New Testament
python3 build_lxx.py sources/lxx-swete sources/brenton sources/treebank_data/v2.1/Greek/texts build/texts.db \
  sources/macula-greek/SBLGNT/tsv/macula-greek-SBLGNT.tsv sources/shortdefs/shortdefsGreekEnglishLogeion \
  > build/lxx_report.json
# the Greek New Testament (SBLGNT + MACULA Greek + Berean Standard Bible)
python3 build_nt.py sources/sblgnt sources/macula-greek sources/bible_databases/formats/csv/BSB.csv build/texts.db \
  > build/nt_report.json
# the Gospel of Nicodemus (Acts of Pilate + Descent into Hell): Tischendorf's Greek, transcribed into
# pipeline/data; Walker's English
python3 build_apocrypha.py build/texts.db sources/treebank_data/v2.1/Greek/texts \
  sources/macula-greek/SBLGNT/tsv/macula-greek-SBLGNT.tsv > build/apocrypha_report.json
# Latin: the Aeneid and the Vulgate (with its verse map to the LXX and the NT, so after them)
python3 build_latin.py sources build/texts.db > build/latin_report.json
# the Hebrew Bible (OSHB), with verse links to the LXX and the Vulgate (so after both)
python3 build_hebrew.py sources build/texts.db > build/hebrew_report.json
# the Bhagavad Gītā (Digital Corpus of Sanskrit, verse-numbered; Besant's English)
python3 build_sanskrit.py sources build/texts.db > build/sanskrit_report.json
# seven principal Upanishads (DCS; Müller's English)
python3 build_upanishads.py sources build/texts.db > build/upanishads_report.json
# the Sahidic NT (Sahidic Bible 2, gaps from Horner; analyses cached in data/coptic_nlp)
python3 build_sahidic.py build sources/bible_databases/formats/csv/CopSahBible2.csv \
  sources/bible_databases/formats/csv/BSB.csv build/texts.db > build/sahidic_report.json
python3 build_coptic.py sources/coptic-scriptorium build/texts.db > build/coptic_report.json
# Nag Hammadi and Berlin Codex texts from Marcion (downloaded by hand into
# sources/marcion; their analyses are cached in data/coptic_nlp)
marcion=()
for f in NagHammadi CodexAkhmim; do
  [ -f "sources/marcion/$f.msql.bz2" ] && marcion+=("sources/marcion/$f.msql.bz2")
done
if [ ${#marcion[@]} -gt 0 ]; then
  python3 build_marcion.py build/texts.db "${marcion[@]}" > build/marcion_report.json
else
  echo "note: no Marcion text dumps in sources/marcion; building without Nag Hammadi"
fi
crum=sources/marcion/cop-3357-8977-3.msql.bz2
[ -f "$crum" ] || { echo "note: $crum not found; building without Crum"; crum=""; }
# Autenrieth: one file from Perseus, fetched by hand (see README)
aut=sources/autenrieth/autenrieth.xml
[ -f "$aut" ] || { echo "note: $aut not found; building without Autenrieth"; aut=""; }
# Old English: Beowulf, lemmatised from Klaeber's glossary
python3 build_oldenglish.py sources build/texts.db > build/oldenglish_report.json
# Old Norse: the Poetic Edda (Pettit), the Prose Edda, Njáls saga and Egils saga (all downloads)
python3 build_oldnorse.py sources build/texts.db > build/oldnorse_report.json
# Bosworth–Toller as entries (madeleineth/btc_anglo_saxon's parser, MIT)
[ -f build/oe_bt.json ] || bzip2 -ckd sources/btc_anglo_saxon/db/oe_bosworthtoller.txt.bz2 \
  | python3 sources/btc_anglo_saxon/db/parse_scanned_bt.py > build/oe_bt.json
python3 build_lexicon.py sources/LSJLogeion sources/MiddleLiddell \
  sources/shortdefs/shortdefsGreekEnglishLogeion build/texts.db build/lexicon.db \
  sources/kellia-dictionary/xml/Comprehensive_Coptic_Lexicon-v1.2-2020.xml "$crum" "$aut" \
  sources/abbott-smith/abbott-smith.tei.xml \
  sources/perseus-lexica/CTS_XML_TEI/perseus/pdllex/lat/ls/lat.ls.perseus-eng2.xml \
  sources/perseus-lexica/CTS_XML_TEI/perseus/pdllex/lat/viaf2845558/viaf001/viaf2845558.viaf001.xml \
  sources/shortdefs/LogeionLatinshortdefs.txt \
  sources/canonical-angLit/data/anon/klaeber_glossary/anon.klaeber_glossary.perseus-mul1.xml build/oe_bt.json \
  sources/HebrewLexicon sources \
  > build/lexicon_report.json
# the Old Norse dictionaries: a downloadable module of their own (lexicon_non.db), not in lexicon.db
python3 build_lexicon_non.py sources build/texts.db build/lexicon_non.db > build/lexicon_non_report.json
# the app ships a compact copy of texts.db (shared lemma/tag rows, no stored word forms)
rm -f build/texts_app.db
# second aorists for flashcards: Morpheus stem types, cached in data/ (refreshed only with MORPHEUS set)
[ -n "${MORPHEUS:-}" ] && python3 aorists.py build/texts.db
python3 compact_texts.py build/texts.db build/texts_app.db build/lexicon.db build/lexicon_non.db
python3 stamp_build.py build/texts_app.db build/lexicon_non.db
# the app ships the default texts (defaults.py), compressed: on first launch it
# inflates them into its own library database, which texts are added to and
# removed from. Every dictionary ships as is.
python3 export_module.py build/texts_app.db build/texts_default.db --defaults --deflate "$out/texts.db.z"
rm -f "$out/texts.db"
# a downloadable module per work, and the catalog of every text on offer
python3 make_modules.py build/texts_app.db build/modules --dictionary non=build/lexicon_non.db
# the modules are published as a GitHub Release per build (publish_release.sh);
# set DOWNLOADS_URL= (empty) for a build that won't be published
release_url='https://github.com/biganemone/ancient-languages/releases/download/texts-{build}'
python3 make_catalog.py build/texts_app.db build/texts_default.db build/modules "$out/catalog.json" \
  "${DOWNLOADS_URL-$release_url}"
cp build/lexicon.db "$out/"
echo "Built: $(du -h "$out"/*.db "$out"/*.db.z | tr '\n' ' ')"
echo "Next: pipeline/publish_release.sh, then build the app in Xcode"
echo "Reports: pipeline/build/*_report.json"
