# Greek Reader

An iPhone/iPad app for reading Ancient Greek with the Perseus texts: tap a word to see its parse, a short definition, and the full entry in LSJ or Middle Liddell. It also offers English translation blocks interleaved with the Greek.

Status: **reader prototype.** It contains Iliad 1 and Plato's *Euthyphro*, built by the data pipeline.

## Getting started

1. **Build the data** (Python 3.10+, `pip install lxml`, `git`):
   ```
   pipeline/build.sh
   ```
   The first run fetches about 150 MB of sources into `pipeline/sources/`. It then writes `texts.db` and `lexicon.db` into `app/GreekReader/Resources/Databases/`. All three locations are git-ignored.
2. **Open `app/GreekReader.xcodeproj`** in Xcode 16 or later and run it on a simulator. To run on a device, choose your team under *Signing & Capabilities* first.

The app needs iOS 17 or later. It has no third-party Swift dependencies: it uses the system SQLite and WebKit.

## Layout

```
pipeline/   Python: Perseus TEI + treebank + Logeion lexica -> SQLite
app/        SwiftUI app (the Xcode project uses folder-synchronised groups,
            so files added under app/GreekReader/ are picked up automatically)
```

## Licences

- **Code:** MIT (see LICENSE).
- **Data built by the pipeline:** CC BY-SA. This covers the Perseus Digital Library texts, translations and treebank (Tufts University). It also covers the LSJ, Middle Liddell and short definitions in the Logeion editions by Helma Dik. The data is not committed here; the pipeline downloads it.
- **Font:** Gentium Book Plus by SIL International, under the SIL Open Font License (`app/GreekReader/Resources/Fonts/Gentium-OFL.txt`).
