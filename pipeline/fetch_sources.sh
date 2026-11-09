#!/usr/bin/env bash
# Fetch the source data into ./sources (sparse, blobless clones; re-running
# only fetches files that are new in works.py).
set -euo pipefail
cd "$(dirname "$0")"
here="$(pwd)"
mkdir -p sources && cd sources

clone() {  # repo dir paths...
  local repo=$1 dir=$2; shift 2
  [ -d "$dir/.git" ] || git clone -q --depth 1 --filter=blob:none --no-checkout "https://github.com/$repo.git" "$dir"
  git -C "$dir" -c gc.auto=0 checkout -q HEAD -- "$@"
}

texts=$(cd "$here" && python3 -c "from works import source_files; print(' '.join(source_files('')))")
treebanks=$(cd "$here" && python3 -c "from works import treebank_files; print(' '.join('v2.1/Greek/texts/' + f for f in treebank_files()))")

clone PerseusDL/canonical-greekLit canonical-greekLit $texts
clone PerseusDL/treebank_data treebank_data $treebanks
# Vanessa Gorman's treebanks (file names contain spaces, hence the array)
gorman=()
while IFS= read -r f; do gorman+=("xml versions/$f"); done \
  < <(cd "$here" && python3 -c "from works import gorman_files; print('\n'.join(gorman_files()))")
clone vgorman1/Greek-Dependency-Trees gorman "${gorman[@]}"
# Greek New Testament: SBLGNT text, MACULA Greek analyses, the Berean Standard Bible,
# Abbott-Smith's lexicon
clone LogosBible/SBLGNT sblgnt data/sblgnt/xml
clone Clear-Bible/macula-greek macula-greek SBLGNT/tsv/macula-greek-SBLGNT.tsv LICENSE.md
clone scrollmapper/bible_databases bible_databases formats/csv/BSB.csv
clone translatable-exegetical-tools/Abbott-Smith abbott-smith abbott-smith.tei.xml
# Septuagint: Swete's text (First1KGreek transcription), the Updated Brenton English (CC0)
clone nathans/lxx-swete lxx-swete data README.md
clone curran-gehring/modern-brenton-septuagint brenton data/source/usfm LICENSE
# Latin: the Aeneid (Perseus) and its treebank, the Clementine Vulgate and Douay-Rheims,
# the PROIEL Latin treebanks, Lewis & Short and Lewis's Elementary Latin Dictionary
clone PerseusDL/canonical-latinLit canonical-latinLit data/phi0690/phi003
# …Ovid's Metamorphoses, Cicero (In Catilinam, De Amicitia), Tacitus (Agricola, Germania, Annals 1)
latin=$(cd "$here" && python3 -c "from build_latin import perseus_latin_files; print(' '.join(perseus_latin_files()))")
git -C canonical-latinLit -c gc.auto=0 checkout -q HEAD -- $latin
git -C treebank_data -c gc.auto=0 checkout -q HEAD -- v2.1/Latin/texts/phi0959.phi006.perseus-lat1.tb.xml \
  v2.1/Latin/texts/phi0474.phi013.perseus-lat1.tb.xml
git -C treebank_data -c gc.auto=0 checkout -q HEAD -- v2.1/Latin/texts/phi0690.phi003.perseus-lat1.tb.xml
git -C bible_databases -c gc.auto=0 checkout -q HEAD -- formats/csv/VulgClementine.csv formats/csv/DRC.csv \
  formats/csv/CopSahBible2.csv     # Sahidic Bible 2 (CC BY-SA): the Sahidic NT
clone syntacticus/syntacticus-treebank-data syntacticus proiel/latin-nt.xml proiel/caes-gal.xml \
  proiel/cic-att.xml proiel/cic-off.xml proiel/README.md
clone PerseusDL/lexica perseus-lexica CTS_XML_TEI/perseus/pdllex/lat/ls/lat.ls.perseus-eng2.xml \
  CTS_XML_TEI/perseus/pdllex/lat/viaf2845558/viaf001/viaf2845558.viaf001.xml
clone helmadik/LSJLogeion LSJLogeion .
clone helmadik/MiddleLiddell MiddleLiddell .
clone helmadik/shortdefs shortdefs .

# Coptic: texts from Coptic SCRIPTORIUM, the Comprehensive Coptic Lexicon from KELLIA.
# (Marcion files - Nag Hammadi texts, Crum - are downloaded by hand into sources/marcion/;
#  SourceForge refuses automated downloads.)
coptic_texts=$(cd "$here" && python3 -c "from build_coptic import WORKS, paths; print(' '.join(p for w in WORKS for p in paths(w)))")
clone CopticScriptorium/corpora coptic-scriptorium $coptic_texts
clone KELLIA/dictionary kellia-dictionary xml/Comprehensive_Coptic_Lexicon-v1.2-2020.xml

# Hebrew: the Open Scriptures Hebrew Bible (WLC + morphology), its lexicon (BDB, Strong's),
# and STEPBible's brief lexicon (TBESH) for one-line glosses
clone openscriptures/morphhb morphhb wlc LICENSE.md
clone openscriptures/HebrewLexicon HebrewLexicon BrownDriverBriggs.xml HebrewStrong.xml LexicalIndex.xml \
  AugIndex.xml readme.md
clone STEPBible/STEPBible-Data STEPBible-Data \
  "Lexicons/TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt"

# Old English: Beowulf (Klaeber's text and glossary, Garnett's translation) from Perseus;
# Bosworth–Toller (Germanic Lexicon Project text) and the MIT script that splits it into entries
clone PerseusDL/canonical-angLit canonical-angLit data/anon/beowulf/anon.beowulf.perseus-ang1.xml \
  data/anon/beowulf/anon.beowulf.perseus-eng1.xml data/anon/klaeber_glossary/anon.klaeber_glossary.perseus-mul1.xml
# The rest of the poetry: the ASPR electronic text (Hidley), via the Classical Language Toolkit.
# (Word readings from Tichý's generator are kept in data/oe_forms.tsv.gz; see oe_forms.py to refresh.)
clone cltk/old_english_text_sacred_texts cltk_oe html README.md
clone madeleineth/btc_anglo_saxon btc_anglo_saxon db/oe_bosworthtoller.txt.bz2 db/parse_scanned_bt.py \
  db/normalize.py LICENSE.md

# Sanskrit: the Digital Corpus of Sanskrit (Hellwig, CC BY 4.0): the Bhagavad Gītā (MBh 6, "BhaGī")
# and its lemma dictionary; gita/gita's verse-numbered text (the Unlicense) for verse divisions;
# Macdonell and Monier-Williams from the Cologne Digital Sanskrit Dictionaries (CC BY-SA 4.0).
# (Besant's English is kept in data/besant_gita.json.gz; Müller's Upanishads in data/upanishads_muller.json.gz,
# Muṇḍaka and Śvetāśvatara's numbered text from Sanskrit Wikisource in data/upanishads_sa_wikisource.json.gz.)
clone OliverHellwig/sanskrit dcs ":(glob)dcs/data/conllu/files/Mahābhārata/*BhaGī*.conllu" \
  dcs/data/conllu/lookup/dictionary.csv dcs/data/readme.md
# …the principal Upanishads in DCS, and the commentaries whose mūla text numbers their sections
for u in Kaṭhopaniṣad Muṇḍakopaniṣad Taittirīyopaniṣad Aitareyopaniṣad Chāndogyopaniṣad Bṛhadāraṇyakopaniṣad \
         Śvetāśvataropaniṣad; do
  git -C dcs -c gc.auto=0 checkout -q HEAD -- ":(glob)dcs/data/conllu/files/$u/*.conllu"
done
git -C dcs -c gc.auto=0 checkout -q HEAD -- corpus/GRETIL/sa_aitareyopaniSad-comm.txt \
  corpus/GRETIL/sa_bRhadAraNyakopaniSadkANva-recension-comm.txt corpus/GRETIL/sa_chAndogyopaniSad-comm.txt \
  corpus/GRETIL/sa_taittirIyopaniSad-zaMkarabhASya.txt corpus/GRETIL/sa_zaMkara-kaThopaniSadbhASya.txt
clone gita/gita gita data/verse.json LICENSE
clone sanskrit-lexicon/csl-orig csl-orig v02/md/md.txt v02/mw/mw.txt LICENSE
