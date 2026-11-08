# Ancient Languages data pipeline

Builds the app's texts, dictionaries, downloadable modules and catalogue from Perseus, Logeion and the other sources below:

- Perseus TEI texts and translations become aligned Greek/English blocks.
- Words get parses: from the Perseus treebank (or Vanessa Gorman's treebanks) where they exist, otherwise from Morpheus.
- Lemmas are linked to Logeion short definitions, LSJ and Middle Liddell (and Autenrieth and Abbott-Smith).
- The Greek New Testament: SBLGNT with MACULA Greek's analyses and the Berean Standard Bible.
- Coptic: the Gospel of Thomas from Coptic SCRIPTORIUM; the rest of the Nag Hammadi
  Library and the Berlin Codex (BG 8502) from Marcion, analysed with the Coptic
  SCRIPTORIUM NLP tools; lemmas linked to the Comprehensive Coptic Lexicon and Crum.

```
./build.sh             # fetch sources (first run), build texts.db.z + lexicon.db + catalog.json into the app,
                       # and the modules into build/modules/
./publish_release.sh   # publish the modules as this build's GitHub Release (see the top-level README)
```

The only Python dependency is `lxml`; Python 3.10 or later is needed. `works.py` lists the texts. Add a work there and re-run.

| File | What it does |
|---|---|
| `works.py` | The work list: TEI versions, English translation, how blocks align, and the treebank file if there is one. |
| `greek.py` | Normalisation keys (lexicon lookup, treebank alignment), the tokenizer, and Beta Code conversion. |
| `tei.py` | Flattens TEI to text plus positioned milestones. |
| `build_texts.py` | Builds `texts.db`: works, `block` (alignment unit plus English), `segment` (verse line, or prose paragraph within a Stephanus section), `token` (UTF-16 offsets, lemma, postag, source) and `analysis` (Morpheus readings). |
| `morpheus.py` | Runs Morpheus at build time only; it never ships. It caches results in `data/morpheus_cache.tsv.gz`. |
| `coptic.py` | Coptic lookup keys, Coptic SCRIPTORIUM tags, readers for the Comprehensive Coptic Lexicon and Marcion's Crum. |
| `build_coptic.py` | Adds Coptic SCRIPTORIUM works (`.tt` files) to `texts.db`: a token per bound group, its morphemes in `morph`. |
| `marcion.py` | Reads Marcion's MySQL dumps and decodes their Coptic transcriptions (format 2 checked against Coptic SCRIPTORIUM's Thomas: 99.4% of letters agree). |
| `coptic_nlp_cache.py` | Runs the Coptic SCRIPTORIUM NLP pipeline over Marcion texts and caches the analyses in `data/coptic_nlp/` (committed). Only needed when the texts change; setup notes are in the file. |
| `build_marcion.py` | Adds the Marcion texts, line by line and cited by codex page and line, with the cached analyses. |
| `compact_texts.py` | Writes the compact `texts.db` the app ships (about half the size): word forms are read from the segment text, lemmas, tags and parses are stored once, and each work's tokens are one id range. It also adds what flashcards need: glosses (from `lexicon.db`), function-word flags, second-aorist entries and each book's token range. |
| `aorists.py` | Morpheus stem types for every aorist form (cached in `data/morpheus_aorists.tsv.gz`), so flashcards can give second aorists (εἶπον, ἦλθον, ἔβην) cards of their own. Needs `MORPHEUS` only when new forms appear. |
| `fsrs_check.py` | A Python twin of the app's FSRS scheduler, for checking its numbers. |
| `build_nt.py` | Adds the Greek New Testament: the SBLGNT's text and paragraphs, MACULA Greek's lemmas and morphology (aligned word for word), and the Berean Standard Bible as the English. A work per book, a part per chapter, a segment per verse ("5.3"). |
| `build_lxx.py` | Adds the Septuagint: Swete's text (First1KGreek transcription), Morpheus parses (ranked with NT usage; NT forms for names), and the Updated Brenton English, aligned verse by verse by length and number (Proverbs and Sirach, whose order differs, are re-paired by shared vocabulary). |
| `latin.py` | Latin lookup keys (case, macrons, æ/œ, i/j, u/v ignored), the tokenizer, PROIEL → AGDT tags. |
| `build_latin.py` | Adds the Aeneid (Perseus; treebank for 6.1–295, Morpheus for the rest) and the Clementine Vulgate with the Douay-Rheims (PROIEL treebank for most of the NT, Morpheus elsewhere), and the `parallel` verse map Vulgate ↔ LXX / Greek NT, aligned through the two English translations. Runs after `build_lxx.py` and `build_nt.py`. Also (PERSEUS_LATIN) Caesar's Gallic War (PROIEL treebank for much of Books 1–6), Ovid's Metamorphoses, Cicero's In Catilinam and De Amicitia, and Tacitus's Agricola, Germania and Annals 1, from Perseus, with the AGLDT treebank where it covers them. |
| `build_sahidic.py` | Adds the Sahidic New Testament: Sahidic Bible 2 (the INTF's transcriptions of the main manuscripts, CC BY-SA), with Horner's text (`data/horner_sahidic_nt.tsv.gz`, extracted from the CrossWire module CopSahHorner, public domain) for the verses it lacks; Coptic SCRIPTORIUM NLP analyses cached in `data/coptic_nlp/sahidic-bible-2.json.gz` (`analyse` mode refreshes them); BSB English; verse links to the Greek NT. |
| `build_oldenglish.py` | Adds Old English: *Beowulf* (Klaeber's text, Garnett's line-for-line translation; Perseus, CC BY-SA), in sentence blocks; lemmas and parses from Klaeber's glossary, which cites nearly every word by line (`oldenglish.py`). |
| `aspr.py`, `oe_forms.py` | The rest of the Old English poetry (ASPR, Hidley's e-text via CLTK), grouped by manuscript, and its automatic lemmas/parses: Beowulf's analyses, then Tichý's generated forms of Bosworth–Toller headwords (`data/oe_forms.tsv.gz`, CC BY 4.0), ranked by corpus lemma frequency (EM). |
| `oe_translations.py` | Public-domain English for 31 of the poems (Faust & Thompson, Garnett, Root, Pitman; Project Gutenberg, saved by browser), cut into numbered lines: `data/oe_translations.json.gz`, read by `build_oldenglish.py`. |
| `build_hebrew.py`, `hebrew.py` | The Hebrew Bible: WLC with OSHB lemmas and morphology (CC BY 4.0), one block per verse in Tanakh order (Torah, Prophets, Writings), words split into morphemes (prefixes, word, suffixes) like Coptic; BSB English through the WLC→English verse map; verse links to the LXX and Vulgate via English alignment. Lexica: BDB and Strong's (OSHB lexicon), glosses from STEPBible TBESH. |
| `build_sanskrit.py`, `sanskrit.py` | The Bhagavad Gītā: the Digital Corpus of Sanskrit's text and analyses (CC BY 4.0), aligned letter by letter with gita/gita's numbered text for verse and half-verse divisions; sandhi groups split as a printed IAST text would, each piece a token whose words are morph rows; Besant's English (1922, `data/besant_gita.json.gz`, from Wikisource). Lexica: Macdonell (whole) and Monier-Williams (entries the lemmas reach), Cologne CC BY-SA 4.0; short glosses from the DCS lemma dictionary. |
| `build_upanishads.py`, `upanishad_editions.py` | Kaṭha, Muṇḍaka, Taittirīya, Aitareya, Chāndogya, Bṛhadāraṇyaka and Śvetāśvatara Upaniṣads from DCS, sectioned by DCS's counters (Kaṭha) or by alignment with numbered texts (Śaṅkara's commentaries' mūla, from the DCS repository's GRETIL folder; Sanskrit Wikisource for Muṇḍaka and Śvetāśvatara, `data/upanishads_sa_wikisource.json.gz`); Müller's English (SBE 1, 15; `data/upanishads_muller.json.gz`, from sacred-texts.com). |
| `build_lexicon.py` | Builds `lexicon.db`: entries stored as raw DEFLATE (Apple's `COMPRESSION_ZLIB`), short definitions, and a `resolve` table from every lemma to its entries. It also prints a coverage report. |
| `defaults.py` | The texts the app ships with (by URN, author or language); everything else becomes a download. |
| `stamp_build.py` | Gives the full build (`texts_app.db`) its build id, in a `meta` table that every export copies. |
| `export_module.py` | Exports chosen works (by URN, author or language, or `--defaults`) as a standalone database with everything they refer to, keeping the full build's row ids so the app can copy them into its library. `--deflate` also writes the raw-DEFLATE copy the app bundles (`texts.db.z`). |
| `make_modules.py` | One downloadable module per work in `build/modules/` (`<id>.db.z`), and `modules.json` with sizes and SHA-256s. Resumable (`--max-seconds`). |
| `make_catalog.py` | `catalog.json`: every work, whether it ships, its module, size and checksum, the build id, and the download URL (`{build}` filled in). |
| `release_notes.py`, `publish_release.sh` | Publish the modules as the GitHub Release `texts-<build>` (see the top-level README, *Publishing texts*). |
| `tests/check_modules.py` | Repeats the app's add/remove SQL on a copy of the library, to check modules before publishing. |

## Alignment

| Text | English block |
|---|---|
| Homer | Murray's 5-line milestones |
| Sophocles | Perseus "cards" (about 10–30 lines, at speech breaks) |
| Plato | Stephanus sections |
| Herodotus, Thucydides | chapters (cited book.chapter.section) |
| Josephus | Whiston's chunks, each starting at a Niese section (cited book.section) |

## Morpheus (only needed when adding texts without a treebank)

Latin uses the same checkout: build its stems too (`cd stemlib/Latin && PATH="$PATH:../../bin" MORPHLIB=.. make`).
Latin results are cached in `data/morpheus_latin_cache.tsv.gz`.

```
git clone https://github.com/perseids-tools/morpheus && cd morpheus/src
make clean && CFLAGS='-std=gnu89 -fcommon -w' make && make install     # Linux; needs flex
cd ../stemlib/Greek && PATH="$PATH:../../bin" MORPHLIB=.. make && PATH="$PATH:../../bin" MORPHLIB=.. make
MORPHEUS=/path/to/morpheus ./build.sh
```

On macOS, use `CFLAGS='-std=gnu89 -Wno-return-type -Wno-implicit-function-declaration' make LOADLIBES='-ll'` instead, per the Morpheus README.

## Autenrieth

Perseus serves the whole of Autenrieth's *Homeric Dictionary* as one TEI file:
`https://www.perseus.tufts.edu/hopper/dltext?doc=Perseus:text:1999.04.0073` (about 4.3 MB).
Save it as `sources/autenrieth/autenrieth.xml`. Its Greek is Beta Code; `build_lexicon.py`
converts it, keeping Autenrieth's long-vowel marks in the entries. Because Autenrieth uses
Homer's Ionic forms (βίη, ξεῖνος), Attic lemmas from the treebank are also tried in their
Homeric spelling (`homeric_candidates`). About 98% of words in Homer find an entry.
In the app Autenrieth is the default lexicon for Homer (and later Hesiod and the Hymns);
where it has no entry, the card shows LSJ.

## Coptic sources

`fetch_sources.sh` gets Coptic SCRIPTORIUM and the KELLIA lexicon. Marcion's files come from
SourceForge (marcion.sourceforge.net) by hand, into `sources/marcion/`:
`NagHammadi.msql.bz2`, `CodexAkhmim.msql.bz2` and `cop-3357-8977-3.msql.bz2` (Crum).
Without them the build leaves out the Nag Hammadi texts and Crum.

The analyses are automatic and unchecked. The tools are trained on Sahidic, so expect
more errors in the Lycopolitan texts (NHC I, X, XI).

## Licences

- Perseus texts and treebank: CC BY-SA 3.0.
- Logeion LSJ, Middle Liddell and short definitions: CC BY-SA. Credit Perseus/Tufts and Helma Dik/Logeion.
- Autenrieth (Perseus): CC BY-SA 3.0. Credit Perseus/Tufts.
- Vanessa Gorman's Greek dependency treebanks (Plato's *Apology* and *Crito*, Thucydides 1 and 3.1–40, *Jewish War* 1.1–512): CC BY-SA 4.0.
- SBL Greek New Testament: CC BY 4.0 (Society of Biblical Literature and Logos Bible Software).
- MACULA Greek Linguistic Datasets (Biblica): CC BY 4.0. Credit "MACULA Greek Linguistic Datasets, available at https://github.com/Clear-Bible/macula-greek/".
- Berean Standard Bible: public domain (from scrollmapper/bible_databases, MIT).
- Abbott-Smith, *A Manual Greek Lexicon of the New Testament* (1922), TEI by the Abbott-Smith project: public domain.
- Swete's Septuagint, First1KGreek transcription (via nathans/lxx-swete): CC BY-SA 4.0.
- Updated Brenton English Septuagint (Brenton 1851, updates by Adam Boyd 2020): CC0.
- Perseus Latin texts, Latin treebank, Lewis & Short and Lewis's Elementary Latin Dictionary: CC BY-SA. Logeion Latin short definitions (Helma Dik): CC BY-SA.
- Clementine Vulgate, Douay-Rheims (Challoner): public domain (via scrollmapper/bible_databases, MIT).
- PROIEL treebank (Jerome's Vulgate, Caesar, Cicero; Dag Haug et al.): CC BY-NC-SA 4.0. Non-commercial, fine for this app.
- Sahidic Bible 2 (Askeland, Schulz; INTF): CC BY-SA. Horner's Sahidic NT (1911–24): public domain.
- Morpheus: MPL-2.0. It is used only at build time.
- Coptic SCRIPTORIUM texts: CC BY (per document); their NLP tools: Apache 2.0, build time only.
- Comprehensive Coptic Lexicon (KELLIA): CC BY-SA 4.0.
- Marcion texts and Crum (Milan Konvička): GPL v2. Credit Marcion wherever its material appears.
- Westminster Leningrad Codex: public domain. Open Scriptures Hebrew Bible (morphology) and Hebrew Lexicon (BDB, Strong's): CC BY 4.0. STEPBible TBESH glosses: CC BY 4.0.
- Digital Corpus of Sanskrit (Oliver Hellwig): CC BY 4.0. gita/gita verse numbering: the Unlicense. GRETIL mūla texts and Sanskrit Wikisource: used for numbering and the few missing passages.
- Cologne Digital Sanskrit Dictionaries (Macdonell, Monier-Williams): CC BY-SA 4.0.
- Besant's Gītā (1922, Wikisource), Müller's Upaniṣads (SBE 1, 15; sacred-texts.com), Long's Marcus Aurelius (1862, Project Gutenberg): public domain.
- Beowulf (Klaeber's text and glossary, Garnett's translation; Perseus): CC BY-SA. ASPR e-text (Greg Hidley, Oxford Text Archive, via CLTK): CC BY-SA. Tichý's Old English forms: CC BY 4.0. Bosworth–Toller (Germanic Lexicon Project): public domain; btc_anglo_saxon: MIT. Old English translations from Project Gutenberg: public domain.
