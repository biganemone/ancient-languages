"""Numbered texts of the Upanishads, used to divide DCS's text into sections
and verses (DCS gives sentences; only some chapters carry section counters).

- Kaṭha and the prose Upanishads (Aitareya, Bṛhadāraṇyaka, Chāndogya, Taittirīya): the
  mūla text in Śaṅkara's commentaries (GRETIL e-texts, carried in the DCS
  repository's corpus/GRETIL), each section numbered "1,2.3" (adhyāya,
  brāhmaṇa/khaṇḍa . section). Aitareya's chapters 2 and 3 are "2.1"–"3.4".
- Muṇḍaka and Śvetāśvatara: Sanskrit Wikisource, verses numbered "॥ १.१.१ ॥"
  (Muṇḍaka) or "॥ १ ॥" within each chapter's page (Śvetāśvatara); kept in
  data/upanishads_sa_wikisource.json.gz (CC BY-SA; the texts are public domain).

Each edition is {chapter key: [(cite, [line, …])]}, the chapter key matching
DCS's chapter label ("BĀU, 1, 3" -> "1.3", "MuṇḍU, 2, 1" -> "2.1",
"ŚvetU, 4" -> "4", "AU, 2, 3" -> "2.3").
"""
import gzip
import json
import os
import re
from collections import OrderedDict

import sanskrit as S

DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def commentary(path, prose=True):
    """{chapter key: [(cite, [lines])]} from a GRETIL commentary's ||mula: lines."""
    out = OrderedDict()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("||mula:"):
                continue
            body = line[len("||mula:"):].strip()
            # a line may hold several numbered sections: "… // 1,1.1 // … // 1,1.2 //"
            for text, num in re.findall(r"(.*?)//\s*([\d,.]+)\s*//", body):
                text = text.strip(" /|")
                if not text:
                    continue
                parts = re.split(r"[,.]", num)
                cite = ".".join(parts)
                key = ".".join(parts[:-1])
                if prose:
                    lines = [" ".join(re.sub(r"\s*[|/]\s*", " ", text).split())]
                else:
                    lines = [p.strip() for p in re.split(r"\s*[|/]\s*", text) if p.strip()]
                out.setdefault(key, []).append((cite, lines))
    return out


def sa_wikisource(path):
    """{"mundaka": {key: [(cite, lines)]}, "svetasvatara": {...}} from the saved pages."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        pages = json.load(f)
    out = {"mundaka": OrderedDict(), "svetasvatara": OrderedDict()}
    for title, text in pages.items():
        name = "mundaka" if title.startswith("मुण्डक") else "svetasvatara"
        chapter = None
        if name == "svetasvatara":
            chapter = str(["प्रथमः", "द्वितीयः", "तृतीयः", "चतुर्थः", "पञ्चमः", "षष्ठः"].index(title.split("/")[1].split()[0]) + 1)
        buf = []
        for raw in text.split("\n"):
            line = re.sub(r"^(॥|\|\|)[^॥|०-९]*(॥|\|\|)\s*", "", raw.strip())      # a chapter title before the first verse
            if line != raw.strip() or "शान्तिः" in line:
                buf = []                          # (a title, or the peace chant: what came before isn't a verse)
            if not line or re.search(r"http|sanskritdocuments|अधिकाध्ययना", line):
                continue
            m = re.search(r"॥\s*([०-९\d.]+)\s*॥", line)
            if not m and ("॥" in line or "शान्तिः" in line):
                buf = []                          # a heading, colophon or the peace chant: not a verse
                continue
            buf.append(line[:m.start()] if m else line)
            if m:
                verse = " ".join(buf)
                verse = re.sub(r"॥[^॥०-९]*॥", " ", verse)             # a title run into the verse
                halves = [S.deva_to_iast(h.strip(" ॥")) for h in re.split(r"\s*।\s*", verse) if h.strip(" ॥")]
                num = m.group(1).translate(DEVA_DIGITS)
                cite = num if name == "mundaka" else f"{chapter}.{num}"
                key = cite.rsplit(".", 1)[0]
                out[name].setdefault(key, []).append((cite, halves))
                buf = []
    return out


def load(sources, data_dir):
    g = os.path.join(sources, "dcs", "corpus", "GRETIL")
    eds = {
        "Aitareyopaniṣad": commentary(os.path.join(g, "sa_aitareyopaniSad-comm.txt")),
        "Bṛhadāraṇyakopaniṣad": commentary(os.path.join(g, "sa_bRhadAraNyakopaniSadkANva-recension-comm.txt")),
        "Chāndogyopaniṣad": commentary(os.path.join(g, "sa_chAndogyopaniSad-comm.txt")),
        "Taittirīyopaniṣad": commentary(os.path.join(g, "sa_taittirIyopaniSad-zaMkarabhASya.txt")),
        # Kaṭha: numbered by vallī (1–6) and verse; verses keep their half-lines
        "Kaṭhopaniṣad": commentary(os.path.join(g, "sa_zaMkara-kaThopaniSadbhASya.txt"), prose=False),
    }
    path = os.path.join(data_dir, "upanishads_sa_wikisource.json.gz")
    if not os.path.exists(path):
        return eds
    sw = sa_wikisource(path)
    eds["Muṇḍakopaniṣad"] = {k: [(c, l) for c, l in v] for k, v in sw["mundaka"].items()}
    eds["Śvetāśvataropaniṣad"] = {k: [(c, l) for c, l in v] for k, v in sw["svetasvatara"].items()}
    return eds
