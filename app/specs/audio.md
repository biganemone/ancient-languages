# Audio (research notes, November 2026)

Status: **not planned.** If we do anything, it will be the **Erasmian Greek New Testament**
(Phemister, below). Everything else here is a record of what we found, so we don't search again.

Constraints we set:
- Nothing bundled with the app. Audio is an optional download (like the text modules), or a link.
- Ideally synced to the text: the verse or line being read is highlighted.
- Erasmian pronunciation preferred; restored (reconstructed) acceptable as a second choice.

## The candidate: Phemister's Greek New Testament

| | |
|---|---|
| Source | archive.org, [`AudiogreeknewtestamentOfWescott.hort.readByMarilynPhemister`](https://archive.org/details/AudiogreeknewtestamentOfWescott.hort.readByMarilynPhemister/) |
| Reader | Marilyn Phemister |
| Text read | Westcott & Hort (1881) |
| Coverage | The whole NT: 260 MP3s (also OGG), one per chapter (`01Matt01.mp3` …), about 24½ hours, 619 MB |
| Licence | **CC BY-NC 3.0 US** (stated on the item page) |
| Pronunciation | Reported as Erasmian, but **not stated** on the page, and the two reviews only say it is "very consistent". **Listen and confirm before building anything.** |

What the licence allows:
- **Redistributing it as an optional download: yes**, with attribution, as long as the app is non-commercial. That's already a condition of the PROIEL and Pettit material, so it adds no new constraint. A paid app or in-app purchase would end this.
- **Syncing it to the text: yes.** There's no "no derivatives" clause, so we can make and ship timing data.
- Credit: "Greek New Testament read by Marilyn Phemister (archive.org), CC BY-NC 3.0 US."

What it would take:
1. **Text mismatch.** We read the SBLGNT, but she reads Westcott–Hort. The two mostly agree, but not everywhere: word-level variants, and passages WH brackets or omits (e.g. the longer ending of Mark, John 7:53–8:11). Verse-level sync tolerates small variants. Verses missing from the audio just don't highlight. We haven't counted the differences.
2. **Timing.** There's none, only chapter files. We'd align each chapter to its verses at build time:
   - **aeneas** (eSpeak NG has a provisional `grc` voice; needs no training): try this first.
   - **MMS forced aligner** (torchaudio `MMS_FA` or ctc-segmentation, on romanized text): the fallback. Its torchaudio API was removed in 2.9, so pin 2.7 or earlier.
   - Either way, spot-check a sample of chapters by ear.
3. **Packaging.** A module per book (audio plus a verse→time table) that the reader downloads from the book's page, like the text modules. Matthew alone is 28 chapters, roughly 65 MB as published. Re-encoding speech at a lower bitrate (e.g. 32 kbps AAC/Opus) would shrink it a lot.
4. **Player.** Play/pause per chapter in the reader, highlight the current verse, tap a verse to seek.

## Other Greek NT audio

| Source | Text | Pronunciation | Licence | Use |
|---|---|---|---|---|
| Andy Martin, [eBible.org](https://ebible.org/multimedia/grc) | Nestle 1904 | not stated | **CC BY-NC-ND 4.0** | 13 books (63% of the NT). eBible's audio ePubs already highlight as they play, so timing exists, but "no derivatives" probably rules out re-timing or re-packaging. Ask permission if we want it. |
| Found in Antiquity, [Matthew 1–5](https://foundinantiquity.com/2022/04/23/the-gospel-of-matthew-greek-audiobook-in-lucian/) | — | restored Koine | CC BY 4.0 | Free to use, but only five chapters. |
| John Schwandt (Accordance/Logos), Pennington (Zondervan), Robinson-Pierpont (Logos) | various | Erasmian | commercial | Link or buy only. |
| koinegreek.com | — | restored Koine | © 2023, patron downloads | Link only. |
| Faith Comes By Hearing (Vavylis), Zodhiates (AMG) | Patriarchal / — | Modern Greek | ℗ / commercial | Link only. |

## Homer and other authors (for the record)

There's **no openly licensed Erasmian Homer.**

- **LibriVox Odyssey 1–24** (Eleni Kemiktsi): public domain, but in Modern Greek pronunciation. Bundling and syncing would be fine. Archive.org items are `odyssey01_1711_librivox` … `odyssey24_1910_librivox`.
- **LibriVox Odyssey 6** (several readers): CC0. Pronunciation unknown.
- **Restored-pronunciation Iliad** (Nagy at Harvard Classics, A. P. David's *Homeric Rhapsody* podcast, Daitz via SORGLL, Luke Ranieri on YouTube): either no licence is stated, or it's commercial (Daitz's complete Homer is sold by Bolchazy-Carducci). These are link-only unless we get permission.
- **Other LibriVox recordings in Ancient Greek, all public domain:**
  - Xenophon's Anabasis and Cyropaedia
  - Thucydides 1–7 (Modern Greek pronunciation)
  - Plato's Apology
  - Hesiod
  - the Homeric and Orphic Hymns

Unverified from that search: the Harvard pages' terms (the site returned 403), the pronunciation of several LibriVox readers, and whether the SORGLL site is still up.
