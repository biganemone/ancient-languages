"""Read Marcion's MySQL text dumps (*.msql.bz2) and decode their Coptic.

Marcion (Milan Konvicka, GPL v2, marcion.sourceforge.net) stores texts in
three encodings, recorded per collection in `library_collection.format`:

  1  Unicode Coptic (already usable; may contain [displayitem] markup)
  2  an upper-case transcription with editorial sigla, used for the Nag
     Hammadi Library and the Berlin Codex (decoded by decode_format2)
  3  a lower-case ASCII transliteration (Sahidic NT, Codex Tchacos, ...)

The format-2 decoding was worked out from the data and checked against
Coptic SCRIPTORIUM's independent edition of the Gospel of Thomas (NHC II,2);
see verify_thomas() for the comparison.
"""
import bz2
import re
import unicodedata

ROW = re.compile(r"insert into `library` \(`book`,`chapter`,`verse`,`text`\) values "
                 r"\((\d+),(\d+),(\d+),'((?:[^'\\]|\\.)*)'\);")
BOOK = re.compile(r"insert into `library_book` \(`id`,`collection`,`name`,`ord`\) values "
                  r"\((\d+),(\d+),'((?:[^'\\]|\\.)*)',(\d+)\);")
COLLECTION = re.compile(r"insert into `library_collection` \(([^)]*)\) values \(([^\n]*?)\);;;")

STROKE = "̄"      # supralinear stroke (as Coptic SCRIPTORIUM writes it)
NOMSAC_OPEN, NOMSAC_CLOSE = "︤", "︥"   # overline over a nomen sacrum
DIAERESIS = "̈"
UNDERDOT = "̣"
CIRCUMFLEX = "̂"
APOSTROPHE = "⳿"  # Coptic morphological divider, the NHC "apostrophe"


def unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def read_dump(path):
    """-> (collection dict, {book_id: (name, order)}, [(book, chapter, verse, text)])"""
    text = bz2.open(path, "rt", encoding="utf-8").read()
    m = COLLECTION.search(text)
    collection = {}
    if m:
        cols = [c.strip("` ") for c in m.group(1).split(",")]
        vals = [v.strip("' ") for v in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", m.group(2))]
        collection = dict(zip(cols, vals))
    books = {int(b): (unescape(name), int(order)) for b, _c, name, order in BOOK.findall(text)}
    rows = [(int(b), int(c), int(v), unescape(t)) for b, c, v, t in ROW.findall(text)]
    rows.sort()
    return collection, books, rows


# ------------------------------------------------------------- format 3 --
F3 = dict(zip("abgdezhqiklmnjoprstufxcwSFKHJGT",
              "ⲁⲃⲅⲇⲉⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭϯ"))


def decode_format3(s):
    return "".join(F3.get(ch, ch) for ch in s)


# ------------------------------------------------------------- format 2 --
F2 = dict(zip("ABGDEZHQIKLMNCOPRSTUFXYWsfhjgtk",
              "ⲁⲃⲅⲇⲉⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϩϫϭϯϧ"))
VOWELS = set("ⲁⲉⲏⲓⲟⲩⲱ")


def decode_format2(s):
    """Returns (coptic text, notes). Notes are editorial remarks such as
    "(Lines 1-3 lacking)", which the app shows separately."""
    notes = []

    def note(m):
        body = m.group(1)
        if body.startswith("`"):           # &`12+-$ : about 12 letters lost
            n = re.sub(r"[^\d]", "", body)
            return f"\x00±{n}\x00" if n else "\x00…\x00"
        if body.strip("() ").lower() != "vacat":
            notes.append(body.strip("() "))
        return ""

    s = re.sub(r"^\d\[[^\]]*\]\d\s*", "", s)   # 1[title page]1
    s = re.sub(r"&([^$]*)\$", note, s)
    s = re.sub(r"^\s*\[1[^\]]*\]1(?!\d)\s*", "", s)   # page/fragment label: [1A]1, [116+21]1
    s = re.sub(r"[\[\]{}<>]\d+", "", s)    # numbered style spans: [2 … ]2, <3 … >3, {2 … }2
    s = re.sub(r"[%#@]\d+", "", s)         # layout/sign codes (paragraph marks, sizes)
    out = []
    pending_stroke = False
    in_nomsac = False
    for i, ch in enumerate(s):
        if ch == "\\":
            pending_stroke = True
            continue
        if ch == "<":
            in_nomsac = True
            continue
        if ch == ">":
            in_nomsac = False
            continue
        letter = F2.get(ch)
        if letter:
            out.append(letter + (STROKE if pending_stroke else "") + (NOMSAC_OPEN if in_nomsac else ""))
            pending_stroke = False
            continue
        pending_stroke = False
        if ch == "+" and out:
            out[-1] = out[-1].replace(NOMSAC_OPEN, "") + DIAERESIS
        elif ch == "?" and out and out[-1][:1] in F2.values():
            out[-1] += UNDERDOT
        elif ch == "=" and out:
            out[-1] += CIRCUMFLEX
        elif ch == "/":
            # after a consonant (or before a line-end hyphen): the NHC
            # "apostrophe"; after a vowel at a word end: a raised point
            prev = out[-1][:1] if out else ""
            nxt = s[i + 1] if i + 1 < len(s) else " "
            out.append("·" if prev in VOWELS and nxt in " \t" else APOSTROPHE)
        elif ch == ":":
            out.append("·")
        elif ch == "{":
            out.append("⟨")
        elif ch == "}":
            out.append("⟩")
        else:
            out.append(ch)
    text = "".join(out)
    # a nomen sacrum overline is written once across the group: ⲓ︤ⲥ︥
    text = re.sub(f"((?:.{NOMSAC_OPEN})+)",
                  lambda m: m.group(1).replace(NOMSAC_OPEN, "")[:1] + NOMSAC_OPEN
                  + m.group(1).replace(NOMSAC_OPEN, "")[1:] + NOMSAC_CLOSE, text)
    # a lacuna inside editorial brackets: "[ ±8 ]" -> "[±8]"
    text = re.sub(r"\[\s*\x00(.*?)\x00\s*\]", r"[\1]", text)
    text = re.sub(r"\[\s*\x00(.*?)\x00\s*", r"[\1 ", text)
    text = re.sub(r"\s*\x00(.*?)\x00\s*\]", r" \1]", text)
    text = re.sub(r"\x00(.*?)\x00", r"[\1]", text)
    text = re.sub(r"(?<=\s)[%#](?=\s)", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return unicodedata.normalize("NFC", text), notes


def decode(text, fmt):
    if fmt == "2":
        return decode_format2(text)
    if fmt == "3":
        return decode_format3(text), []
    # format 1: Unicode, but strip [displayitem]…[enddisplayitem] markup
    text = re.sub(r"\[displayitem\].*?\[enddisplayitem\]", "", text)
    return unicodedata.normalize("NFC", text.strip()), []


def bare(s):
    """Letters only, for comparing editions."""
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if "Ⲁ" <= ch <= "⳿" or "Ϣ" <= ch <= "ϯ").lower()


def verify_thomas(marcion_nh_dump, scriptorium_tt):
    """Compare Marcion's Gospel of Thomas (decoded) with Coptic SCRIPTORIUM's
    edition letter by letter; returns the share of matching letters."""
    import difflib
    _, books, rows = read_dump(marcion_nh_dump)
    tid = next(b for b, (name, _) in books.items() if "Thomas" in name and "II" in name)
    ours = "".join(decode_format2(t)[0] for b, c, v, t in rows if b == tid)
    tt = open(scriptorium_tt, encoding="utf-8").read()
    theirs = "".join(re.findall(r'<orig_group orig_group="([^"]*)"', tt))
    a, b = bare(ours), bare(theirs)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.ratio(), len(a), len(b), ours[:300]


# ------------------------------------------------- tractates for the app --
def is_letter(ch):
    return "Ⲁ" <= ch <= "ⳣ" or "Ϣ" <= ch <= "ϯ"


def book_title(name):
    """'( codex II ) The Gospel of Philip' -> ('II', 'Gospel of Philip')"""
    m = re.match(r"\(\s*codex\s+([IVXL]+)\s*\)\s*(.*)", name)
    codex, title = (m.group(1), m.group(2)) if m else ("", name)
    title = re.sub(r"^The\s+", "", title.strip())
    return codex, title[:1].upper() + title[1:]


def book_lines(rows, book, fmt):
    """-> [{page, line, text, notes}] for one book, in manuscript order.
    Marcion's `chapter` is the codex page and `verse` the line."""
    out = []
    for b, page, line, raw in rows:
        if b != book:
            continue
        text, notes = decode(raw, fmt)
        out.append(dict(page=page, line=line, text=text, notes=notes))
    return out


def nlp_input(lines, lacuna=" "):
    """Running text for the Coptic NLP tools, and where each of its letters
    sits in the edition: (text, [(line index, offset in that line's text)]).

    Only letters, spaces and the raised point go in; brackets, dots for
    illegible letters, accents and the like are left out, and a word broken
    at a line end ("ⲉⲧϥ̄ⲛⲁ-" / "ⲉⲉⲓϥ") is joined up again. A lacuna ("[±8]")
    becomes `lacuna`: a word break, or a raised point to keep the tools from
    joining words across the gap."""
    out, where = [], []
    for li, ln in enumerate(lines):
        text = ln["text"]
        body = text[:-1] if text.endswith("-") else text
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "[" and re.match(r"\[(?:±\d+|…)", body[i:]):
                out.append(lacuna)
                i = body.index("]", i) + 1 if "]" in body[i:] else len(body)
                continue
            if is_letter(ch):
                out.append(ch)
                where.append((li, i))
            elif ch.isspace():
                out.append(" ")
            elif ch == "·":
                out.append(" · ")
            i += 1
        if not text.endswith("-"):
            out.append(" ")
    text = re.sub(r" +", " ", "".join(out)).strip()
    return text, where
