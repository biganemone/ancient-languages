"""Edward Pettit, The Poetic Edda: A Dual-Language Edition (Open Book
Publishers, 2023; DOI 10.11647/OBP.0308; CC BY-NC 4.0), read from its TEI
XML (Loughborough University repository, figshare article 25968073).

One file per poem (ch1.xml … ch36.xml). Each file has, in document order:
  - the introduction (under the chapter head), the Synopsis and Further
    Reading;
  - the Old Norse text, in one or more sections: verse (<l>, a stanza
    starts with a line holding its number, "1. ‘Hljóðs bið ek …"), prose
    (<p>/<quote>), and speaker lines ("Óðinn kvað:", unnumbered <l>);
  - the English, in the same number of sections in the same order;
  - the Textual Apparatus.
The XML's nesting of these sections is unreliable (an InDesign export), so
they are found by walking the heads in document order.

  read(xml_dir) -> [poem], where poem = {
      "n": 1, "title": "Vǫluspá", "english_title": "The Prophecy of the Seeress",
      "items": [item, …]}
  and item = {"kind": "stanza", "n": 1, "lines": [str], "speaker": str|None,
              "english": [str], "english_speaker": str|None, "heading": str|None}
          or {"kind": "prose", "text": str, "english": str, "heading": str|None}
"""
import os
import re

from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"
CAESURA = "  "
SKIP = ("Synopsis", "Further Reading", "Textual Apparatus")
POEMS = 36
CREDIT = ("Text and translation: Edward Pettit, The Poetic Edda: A Dual-Language Edition (Cambridge: Open Book "
          "Publishers, 2023; https://doi.org/10.11647/OBP.0308), CC BY-NC 4.0.")
# "1. ", "30 . ", and "23 [24]. " / "26 [21] " (with another edition's number)
SPEECH = re.compile(r"\b(kvað|kváðu|mælti|svaraði|sagði|kallaði|said|spoke|answered|replied|called|asked)\b")
STANZA_NO = re.compile(r"^\s*(\d+)\s*(?:\[\d+\]\s*)?\.?\s+(?=\S)")


def text_of(el):
    """The text of an element without its footnotes; whitespace tidied, the
    caesura (three no-break spaces) kept as two spaces."""
    parts = []

    def walk(e, top):
        if e.tag == TEI + "note":
            pass
        else:
            parts.append(e.text or "")
            for c in e:
                if isinstance(c.tag, str):
                    walk(c, False)
                else:
                    parts.append(c.tail or "")
        if not top:
            parts.append(e.tail or "")

    walk(el, True)
    s = "".join(parts)
    s = re.sub(r" {2,}", "\u0001", s)                 # caesura
    s = re.sub(r"[ \t\n\r ]+", " ", s).strip()
    return s.replace(" \u0001", "\u0001").replace("\u0001 ", "\u0001").replace("\u0001", CAESURA)


def head_level(h):
    t = h.get("type") or ""
    if t == "chapter":
        return 0
    m = re.search(r"lev(\d)", t)
    return int(m.group(1)) if m else 1


def sections(path):
    """[(heading, [element])] for the text sections of one poem file, in order."""
    root = etree.parse(path).getroot()
    body = root.find(f".//{TEI}body")
    # A level-2 head is a subsection of the Synopsis or the Apparatus (skip),
    # or of a text section; after Further Reading (which has none of its own)
    # it is a prose passage that opens the text ("Frá sonum Hrauðungs konungs").
    out, skipping, cur, lev1 = [], True, None, ""
    for e in body.iter(TEI + "head", TEI + "l", TEI + "p", TEI + "quote"):
        if any(a.tag in (TEI + "note", TEI + "head") for a in e.iterancestors()):
            continue
        if e.tag == TEI + "quote" and any(a.tag == TEI + "quote" for a in e.iterancestors()):
            continue
        if e.tag == TEI + "p" and any(a.tag == TEI + "quote" for a in e.iterancestors()):
            continue
        if e.tag == TEI + "head":
            level, title = head_level(e), text_of(e)
            if level == 0:
                skipping = True
            elif level == 1:
                skipping, lev1 = title.startswith(SKIP), title
            else:
                skipping = lev1.startswith(("Synopsis", "Textual Apparatus"))
            if not skipping:
                cur = (title, [])
                out.append(cur)
            continue
        if not skipping and cur is not None:
            cur[1].append(e)
    return [s for s in out if s[1]]


def all_italic(e):
    """A speaker line ("Óðinn kvað:") is set wholly in italics."""
    kids = [c for c in e if isinstance(c.tag, str) and c.tag not in (TEI + "anchor", TEI + "note")]
    if (e.text or "").strip() or len(kids) != 1 or kids[0].tag != TEI + "hi":
        return False
    return "italic" in (kids[0].get("rendition") or "") and not (kids[0].tail or "").strip()


def is_speaker(e, t, nxt):
    """"Óðinn kvað:", "Þá mælti Skaði:", "Óðinn said:". The markup is not
    consistent (italic or not, indented or not), so go mostly by the words;
    a verse line can end in a colon too ("ok þú, Vafþrúðnir, vitir:"), or
    even in "kvað:" ("unz nauðig reis, nás orð um kvað:")."""
    if not t.endswith(":") or len(t) > 50 or CAESURA in t:
        return False
    words = t.split()
    if SPEECH.search(t) and (len(words) <= 3 or all_italic(e)):
        return True
    return bool(STANZA_NO.match(nxt)) and "\t" not in "".join(e.itertext())


def items(elements, heading):
    """Stanzas and prose paragraphs of one section."""
    out, speaker, first = [], None, True
    texts = [text_of(e) for e in elements]
    for k, e in enumerate(elements):
        t = texts[k]
        if not t:
            continue
        if e.tag == TEI + "l":
            m = STANZA_NO.match(t)
            nxt = next((texts[j] for j in range(k + 1, len(elements)) if texts[j]), "")
            if m:
                out.append({"kind": "stanza", "n": int(m.group(1)), "lines": [t[m.end():].strip()],
                            "speaker": speaker, "heading": heading if first else None})
                speaker, first = None, False
            elif is_speaker(e, t, nxt):
                speaker = t
            elif out and out[-1]["kind"] == "stanza":
                out[-1]["lines"].append(t)
            else:                                  # an unnumbered verse line before any stanza
                out.append({"kind": "stanza", "n": 0, "lines": [t], "speaker": speaker,
                            "heading": heading if first else None})
                speaker, first = None, False
        else:
            out.append({"kind": "prose", "text": t, "heading": heading if first else None})
            first = False
    return out


def read_poem(path, n):
    secs = sections(path)
    if len(secs) % 2:
        raise ValueError(f"{path}: {len(secs)} text sections, expected Old Norse/English pairs: "
                         f"{[h for h, _ in secs]}")
    half = len(secs) // 2
    norse, english = secs[:half], secs[half:]
    root = etree.parse(path).getroot()
    title = text_of(root.find(f".//{TEI}titleStmt/{TEI}title"))
    out = []
    for (nh, nel), (eh, eel) in zip(norse, english):
        ni, ei = items(nel, nh), items(eel, eh)
        e_stanzas = {it["n"]: it for it in ei if it["kind"] == "stanza" and it["n"]}
        e_unnumbered = [it for it in ei if it["kind"] == "stanza" and not it["n"]]
        e_prose = [it for it in ei if it["kind"] == "prose"]
        k = z = 0
        for it in ni:
            if it["kind"] == "stanza":
                if it["n"]:
                    tr = e_stanzas.get(it["n"])
                else:                               # verse without a number: pair in order
                    tr = e_unnumbered[z] if z < len(e_unnumbered) else None
                    z += 1
                it["english"] = tr["lines"] if tr else []
                it["english_speaker"] = tr["speaker"] if tr else None
            else:
                it["english"] = e_prose[k]["text"] if k < len(e_prose) else ""
                k += 1
            out.append(it)
    english_title = english[0][0] if english else ""
    return {"n": n, "title": re.sub(r"\s*\(.*\)$", "", title) if n not in (1, 32) else title,
            "english_title": english_title, "items": out}


def split_restarts(poem):
    """Svipdagsmál is two poems, Gróugaldr and Fjǫlsvinnsmál, each numbered from 1:
    split where the stanza numbers start again, at the section's own heading."""
    out, cur, last = [], [], 0
    for it in poem["items"]:
        if it["kind"] == "stanza" and it["n"] and it["n"] < last and it.get("heading"):
            out.append(cur)
            cur = []
        if it["kind"] == "stanza" and it["n"]:
            last = it["n"]
        cur.append(it)
    out.append(cur)
    if len(out) == 1:
        return [poem]
    return [dict(poem, title=part[0].get("heading") or poem["title"], items=part) for part in out]


def read(xml_dir):
    """The poems in Pettit's order, numbered from 1 (Svipdagsmál's two halves separately)."""
    poems = []
    for n in range(1, POEMS + 1):
        poems.extend(split_restarts(read_poem(os.path.join(xml_dir, f"ch{n}.xml"), n)))
    for k, p in enumerate(poems):
        p["n"] = k + 1
    return poems


if __name__ == "__main__":
    import sys
    poems = read(sys.argv[1])
    for p in poems:
        st = [i for i in p["items"] if i["kind"] == "stanza"]
        pr = [i for i in p["items"] if i["kind"] == "prose"]
        missing = [i["n"] for i in st if not i["english"]]
        print(f'{p["n"]:2} {p["title"][:34]:34} {p["english_title"][:30]:30} stanzas {len(st):3} '
              f'prose {len(pr):2} untranslated {missing[:8]}')
