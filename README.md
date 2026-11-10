# Ancient Languages

A free, open-source iPhone and iPad app for reading ancient texts in the original. Tap a word to see its parse, a short definition, and the full entry in the standard dictionaries. The original is shown with an English translation, aligned passage by passage. Highlights, notes and flashcards (spaced repetition, built from the texts' vocabulary) are included.

It has no ads, accounts or paid features. Everything is built from openly licensed or public-domain sources (see [Licences](#licences)).

Status: **in development** (not yet on the App Store).

## Languages and texts

The app ships with the **default texts** below and every dictionary except Old Norse's, which downloads with the first Old Norse text. The other texts in the catalogue can be added from **Read › Add Texts**: the app downloads each one as a small module (see [Publishing texts](#publishing-texts)). Readers can remove any text or whole language, the defaults included, and add them back later.

| Language | Default texts (ship with the app) | Also available to download | Dictionaries |
|---|---|---|---|
| **Greek** | Homer, *Iliad* and *Odyssey*; Plato, *Euthyphro*, *Apology*, *Crito*; Sophocles, *Antigone*; Herodotus; Marcus Aurelius; the New Testament (SBLGNT) | the rest of Plato and Sophocles; Aeschylus; Euripides (all 19 plays); Aristophanes, *Clouds* and *Birds*; Hesiod and the Homeric Hymns; Apollodorus, *Library* and *Epitome*; Thucydides; Josephus, *Jewish War*; the Septuagint; the Gospel of Nicodemus (Acts of Pilate) | LSJ; Middle Liddell; Autenrieth (Homer); Abbott-Smith (New Testament); Logeion short definitions |
| **Latin** | Vergil, *Aeneid*; Caesar, *Gallic War*; Ovid, *Metamorphoses*; Cicero, *In Catilinam* and *De Amicitia*; Tacitus, *Agricola*, *Germania*, *Annals* 1; the Vulgate | Homer's *Iliad*, *Odyssey* and *Hymns* in the Didot edition's word-for-word Latin (1837–38), line for line with the Greek: read on its own, or shown beside the Greek (Parallel text: Latin) | Lewis & Short; Lewis's Elementary Latin Dictionary |
| **Hebrew** | the Hebrew Bible (Westminster Leningrad Codex): Torah, Prophets, Writings | — | Brown–Driver–Briggs; Strong's; STEPBible glosses |
| **Sanskrit** | *Bhagavad Gītā*; the Kaṭha, Muṇḍaka, Taittirīya, Aitareya, Chāndogya, Bṛhadāraṇyaka and Śvetāśvatara Upaniṣads (IAST or Devanāgarī) | — | Macdonell; Monier-Williams |
| **Coptic** | *Gospel of Thomas* (Coptic SCRIPTORIUM) | the Sahidic New Testament; the rest of the Nag Hammadi Library; the Berlin Codex (BG 8502); fragments of the Acts of Pilate | Comprehensive Coptic Lexicon; Crum |
| **Old English** | *Beowulf* | the rest of the Anglo-Saxon Poetic Records (Junius, Vercelli and Exeter Books, Paris Psalter, Meters of Boethius, minor poems) | Klaeber's *Beowulf* glossary; Bosworth–Toller |
| **Old Norse** | — | the Poetic Edda (Pettit's edition and translation); Snorri's Prose Edda; *Njáls saga*; *Egils saga* | Zoëga; Cleasby–Vigfússon (downloaded with the first Old Norse text) |

In all, 477 texts: 165 ship with the app and 312 are downloads. The default list is `pipeline/defaults.py`. Hebrew and Sanskrit each have their own text-size setting.

Parses come from hand-made treebanks where they exist: Perseus, Gorman, PROIEL, MACULA, OSHB, DCS and Coptic SCRIPTORIUM. Elsewhere they are generated automatically, which is less reliable: by Morpheus for Greek and Latin, by the Coptic SCRIPTORIUM tools for Coptic, from Klaeber's glossary and generated forms for Old English, and from forms generated from Zoëga's headwords for Old Norse.

**Size:** the App Store download is about 185 MB. Installed, the app takes about 400 MB: 250 MB for the app with its dictionaries, and 150 MB for the reader's library, unpacked on first launch.

## Getting started

1. **Build the data.** You need Python 3.10+, `pip install lxml`, and `git`. Then run:
   ```
   pipeline/build.sh
   ```
   - The first run fetches the sources into `pipeline/sources/`, which takes several minutes.
   - It writes `texts.db.z` (the default texts, compressed), `lexicon.db` and `catalog.json` into `app/AncientLanguages/Resources/Databases/`.
   - It writes the downloadable modules into `pipeline/build/modules/`.
   - These locations are git-ignored.
   - A few sources have to be fetched by hand (Marcion's Coptic files, Autenrieth), and Morpheus is needed only when adding texts without a treebank. See [`pipeline/README.md`](pipeline/README.md).
2. **Open `app/AncientLanguages.xcodeproj`** in Xcode 16 or later and run it on a simulator. To run on a device, first choose your team under *Signing & Capabilities*.

The app needs iOS 17 or later. It uses the system SQLite, Compression, CryptoKit and WebKit, and one Swift package of its own, [StudyCore](https://github.com/biganemone/studycore) (SQLite, FSRS, the dictionary reader and entry view), which it shares with a sister app. Xcode fetches StudyCore itself; `Package.resolved` pins the commit. To work on StudyCore alongside the app, drag a local checkout of it into the Xcode project navigator: the local copy overrides the fetched one until you remove it.

## How texts are stored

- **The app bundle** carries:
  - the default texts as `texts.db.z`, a compressed SQLite database;
  - `lexicon.db`;
  - `catalog.json`, which lists every text, its module file, size and SHA-256.
- **On first launch** the app unpacks the default texts into its own library database (`Application Support/Library/library.db`).
- **Adding a text** copies that text's rows into the library: from the bundle for a default text, or from a downloaded module otherwise.
- **Removing a text** deletes its rows. Highlights, notes, reading positions and flashcards are kept.
- **Every data build has a build id.** The app accepts modules only from its own build, because row ids are consistent only within one build.
- **After an app update with a new build**, the library is rebuilt and the reader is offered a re-download of the texts they had downloaded.

## Publishing texts

The downloadable modules are published as a **GitHub Release** of this repository, one release per data build, tagged `texts-<build>` (e.g. `texts-20261107T2230Z`). Each release holds every module (`*.db.z`), `catalog.json`, `modules.json` and `CREDITS.md`. The app downloads from `https://github.com/biganemone/ancient-languages/releases/download/texts-<build>/<module>`.

Whenever the texts change:

1. **Build:** `pipeline/build.sh`. This stamps a new build id and writes the bundled texts, the modules, and a catalogue pointing at that build's release.
2. **Publish:** `pipeline/publish_release.sh`. You need the GitHub CLI, signed in once (`brew install gh`, then `gh auth login`). The script:
   - checks every module against `catalog.json`;
   - creates the release, then uploads the modules in batches. If it is interrupted, run it again and it uploads only what's missing;
   - downloads one module to confirm its checksum.

   `pipeline/publish_release.sh --check` runs the checks without uploading.
3. **Build the app** in Xcode and ship it.

Publish before shipping: an app version can only download from the release for its own build. **Don't delete old releases**, because people on older app versions still download from them. For a local build that won't be published, run `DOWNLOADS_URL= pipeline/build.sh`; the app then offers only the default texts.

## Layout

```
pipeline/   Python: sources → texts, dictionaries, modules, catalogue (see pipeline/README.md)
app/        SwiftUI app (folder-synchronised groups: files added under app/AncientLanguages/ are picked up automatically)
app/specs/  design notes
```

## Licences

- **Code:** MIT (see [LICENSE](LICENSE)).
- **Data:** the texts, translations, analyses and dictionaries are not committed here. The pipeline downloads them, and the app and the release modules redistribute them under their own licences:
  - **CC BY-SA:**
    - Perseus Digital Library texts, translations, treebanks and dictionaries (Tufts University), including LSJ, Middle Liddell and short definitions in Helma Dik's Logeion editions;
    - Gorman's Greek treebanks;
    - Swete's Septuagint (First1KGreek);
    - Sahidic Bible 2 (INTF);
    - the Comprehensive Coptic Lexicon (KELLIA);
    - the Anglo-Saxon Poetic Records e-text (Hidley);
    - the Cologne Sanskrit dictionaries.
  - **CC BY 4.0:**
    - SBL Greek New Testament;
    - MACULA Greek;
    - Open Scriptures Hebrew Bible and Hebrew Lexicon;
    - STEPBible TBESH;
    - Coptic SCRIPTORIUM;
    - the Digital Corpus of Sanskrit (Oliver Hellwig);
    - Tichý's Old English forms;
    - NeuralMIcePaHC (build time only, for the Old Norse texts).
  - **CC BY-NC-SA 4.0:** the PROIEL treebank (Vulgate, Caesar). It is non-commercial, which this project is.
  - **CC BY-NC 4.0:** Edward Pettit's edition and translation of the Poetic Edda (Open Book Publishers, 2023). Also non-commercial.
  - **GPL v2:** the Nag Hammadi and Berlin Codex texts and Crum's dictionary from Marcion (Milan Konvička). Marcion is credited wherever its material appears.
  - **Public domain or CC0:**
    - the Westminster Leningrad Codex;
    - the Clementine Vulgate and Douay-Rheims;
    - the Berean Standard Bible;
    - the Updated Brenton Septuagint;
    - Abbott-Smith;
    - the Didot Latin Homer (Project Gutenberg #52691–52693);
    - Tischendorf's *Evangelia Apocrypha* (1876), whose Greek Gospel of Nicodemus was transcribed for this project (`pipeline/data/acts_of_pilate_tischendorf.txt`);
    - Bosworth–Toller;
    - Finnur Jónsson's editions of the Prose Edda (1907), Njáls saga (1908) and Egils saga (1894), cleaned from the archive.org scans for this project (`pipeline/data/non_texts/`);
    - Zoëga's and Cleasby–Vigfússon's Old Norse dictionaries (digitized by stscoundrel, MIT);
    - Horner's Sahidic New Testament;
    - translations by Long, Besant, Müller, Dasent, Green, Brodeur and others (Project Gutenberg, Wikisource, sacred-texts.com).

  The full credits are shown in the app, at the foot of each language's list, and in each release's `CREDITS.md`. Per-source details are in [`pipeline/README.md`](pipeline/README.md#licences).
- **Build-time tools** (not distributed): Morpheus (MPL-2.0) and the Coptic SCRIPTORIUM NLP tools (Apache 2.0).
- **Fonts:** under the SIL Open Font License, with the licence files in `app/AncientLanguages/Resources/Fonts/`:
  - Gentium Book Plus (SIL International);
  - Noto Serif Hebrew and Noto Sans Coptic (Google).
