"""(How data/upanishads_muller.json.gz was made; kept for reference.)

Max Müller's Upanishads (SBE 1 and 15) -> {key: {cite: English}}.

Input: the pages saved from sacred-texts.com (SBE 15, and the Aitareya part
of SBE 1) and English Wikisource (the Chāndogya, SBE 1), each a list of
(tag, text) items. Sections are numbered "1.", "2." … within each
chapter; chapters are found from headings ("FIRST ADHYÂYA", "SECOND VALLÎ")."""
import json
import re
import sys
from collections import OrderedDict

ORD = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH", "NINTH", "TENTH", "ELEVENTH",
       "TWELFTH", "THIRTEENTH", "FOURTEENTH", "FIFTEENTH", "SIXTEENTH", "SEVENTEENTH", "EIGHTEENTH", "NINETEENTH",
       "TWENTIETH"]


def ordinal(s):
    s = s.upper().replace("-", " ")
    m = re.match(r"\s*(TWENTY|THIRTY)?\s*([A-Z]+)", s)
    if not m:
        return None
    base = {"TWENTY": 20, "THIRTY": 30}.get(m.group(1) or "", 0)
    word = m.group(2)
    if word == "TWENTIETH":
        return 20
    if word in ORD:
        return base + ORD.index(word) + 1
    return None


UNIT = re.compile(r"^\s*([A-Za-z-]+(?:\s+[A-Za-z-]+)?)\s+(ADHY.YA|VALL.|ANUV.KA|BR.HMANA|KHANDA|MUNDAKA|PRAP.THAKA)\b",
                  re.I)


def split_numbered(text):
    """'1. … 2. … 3. …' -> {1: …, 2: …}; numbers must run in order."""
    out, expect, pos, cur = OrderedDict(), 1, 0, None
    for m in re.finditer(r"(?:(?<=\s)|^)\(?(\d{1,2})\s?\.(?=\s)", text):
        n = int(m.group(1))
        if n != expect:
            continue
        if cur is not None:
            out[cur] = text[pos:m.start()].strip()
        cur, pos, expect = n, m.end(), n + 1
    if cur is not None:
        out[cur] = text[pos:].strip()
    return out


def clean(t):
    t = re.sub(r"\[paragraph continues\]\s*", "", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def streams(pages, which):
    """[(upanishad key, chapter tuple, text)] from pages in reading order."""
    cur_up, levels, buf, out = None, {}, [], []

    def flush():
        if cur_up and buf and levels:
            out.append((cur_up, dict(levels), " ".join(buf)))
        buf.clear()

    for page in pages:
        for tag, text in page["items"]:
            t = text.strip()
            up = None
            for key, pat in (("katha", "KATHA-UPANISHAD"), ("mundaka", "MUNDAKA-UPANISHAD"),
                             ("taittiriya", "TAITTIR"), ("brihadaranyaka", "BRIHAD"),
                             ("svetasvatara", "SVET"), ("chandogya", "KH.NDOGYA-UPANISHAD")):
                if re.match(pat, t.upper()) and len(t) < 60:
                    up = key
            if up:
                flush()
                cur_up, levels = up, {}
                continue
            m = UNIT.match(t)
            if m and len(t) < 60:
                n = ordinal(m.group(1))
                if n:
                    flush()
                    unit = m.group(2).upper()
                    unit = re.sub(r"[^A-Z]", "", unit.replace("Â", "A").replace("Î", "I"))
                    levels[unit[:4]] = n
                    # a new higher unit resets the lower ones
                    if unit[:4] in ("ADHY", "MUND", "PRAP") and which != "aitareya":
                        for k in list(levels):
                            if k not in (unit[:4],):
                                if k in ("VALL", "KHAN", "BRAH", "ANUV"):
                                    levels.pop(k)
                    continue
            if tag.startswith("h") or re.match(r"^(layout|Khandas \(not listed)", t):
                continue
            buf.append(t)
    flush()
    return out


def cite_of(up, lv):
    if up == "katha":
        a, v = lv.get("ADHY", 1), lv.get("VALL", 1)
        return f"{a}.{v - 3 if v > 3 else v}"
    if up == "mundaka":
        return f"{lv.get('MUND')}.{lv.get('KHAN')}"
    if up == "taittiriya":
        return f"{lv.get('VALL')}.{lv.get('ANUV')}"
    if up == "brihadaranyaka":
        return f"{lv.get('ADHY')}.{lv.get('BRAH')}"
    if up == "svetasvatara":
        return f"{lv.get('ADHY')}"
    if up == "chandogya":
        return f"{lv.get('PRAP')}.{lv.get('KHAN')}"
    if up == "aitareya":
        a = lv.get("ADHY") - 3            # Aitareya-āraṇyaka II.4–6 = Aitareya Upaniṣad 1–3
        return f"{a}.{lv.get('KHAN')}" if a == 1 else f"{a}"
    return None


def parse(sbe_path, chandogya_path):
    sbe = json.load(open(sbe_path, encoding="utf-8"))
    chu = json.load(open(chandogya_path, encoding="utf-8"))
    result = {}
    groups = [(sbe["the-upanishads-part-ii"], None)]
    groups.append(([{"items": [("h1", "KHÂNDOGYA-UPANISHAD.")] + v} for v in chu.values()], None))
    for pages, _ in groups:
        for up, lv, text in streams(pages, None):
            chap = cite_of(up, lv)
            parts = split_numbered(text) or {1: text}       # a one-section chapter is unnumbered
            for n, t in parts.items():
                result.setdefault(up, OrderedDict())[f"{chap}.{n}"] = clean(t)
    # Aitareya: SBE 1's Aitareya-āraṇyaka II.4–6
    cur = OrderedDict()
    levels = {}
    for p in sbe["the-upanishads-part-1-sbe01"]:
        buf = []
        for tag, t in p["items"]:
            m = UNIT.match(t)
            if m and len(t) < 60 and ordinal(m.group(1)):
                if buf and levels:
                    _store(cur, levels, " ".join(buf))
                buf = []
                levels[re.sub(r"[^A-Z]", "", m.group(2).upper().replace("Â", "A"))[:4]] = ordinal(m.group(1))
                continue
            if tag.startswith("h"):
                continue
            buf.append(t)
        if buf and levels:
            _store(cur, levels, " ".join(buf))
    result["aitareya"] = cur
    return result


def _store(cur, levels, text):
    chap = cite_of("aitareya", levels)
    for n, t in split_numbered(text).items():
        cur[f"{chap}.{n}"] = clean(t)


if __name__ == "__main__":
    r = parse(sys.argv[1], sys.argv[2])
    for k, v in r.items():
        chs = OrderedDict()
        for c in v:
            chs.setdefault(c.rsplit(".", 1)[0], 0)
            chs[c.rsplit(".", 1)[0]] += 1
        print(k, len(v), dict(list(chs.items())[:60]))
    json.dump(r, open(sys.argv[3], "w"), ensure_ascii=False)
