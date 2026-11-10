"""Old Norse texts from scanned public-domain editions: the archive.org hOCR
(word boxes and type sizes) turned into clean running text.

  - Finnur Jónsson, Brennu-Njálssaga (Altnordische Saga-Bibliothek 13, Halle, 1908): archive.org brennunjlssaganj00finn
  - Finnur Jónsson, Egils saga Skallagrímssonar (ASB 3, 2nd ed., 1924): archive.org egilssagaskalla00finn
  - Finnur Jónsson, Edda Snorra Sturlusonar (Reykjavík, 1907): archive.org eddasnorrasturlu00edda

Extraction (this module). The saga text is set in a larger type than the
German notes beneath it (Njála: x_size 77 against 61) and spans the full
measure, while the notes are in two columns; so a page's text lines are the
ones in the body size and the body column. Words outside the column
(marginal references such as "Nj. I.") and the line numbers in the margin
(5, 10, 15 …) are dropped, and words broken at the end of a line are joined.

Correction (non_correct.py) then restores the letters the OCR loses (ǫ read
as o, þ as J) or p, ð as 3 …) and fixes misread words against the
dictionary's forms and a second witness.
"""
import re
import statistics
from collections import Counter

from lxml import etree

BBOX = re.compile(r"bbox (\d+) (\d+) (\d+) (\d+)")
XSIZE = re.compile(r"x_size ([\d.]+)")


class Word:
    __slots__ = ("text", "x0", "y0", "x1", "y1")

    def __init__(self, text, box):
        self.text = text
        self.x0, self.y0, self.x1, self.y1 = box

    def __repr__(self):
        return f"Word({self.text!r} {self.x0}-{self.x1})"


class Line:
    __slots__ = ("words", "size", "x0", "y0", "x1", "y1", "page")

    def __init__(self, words, size, box, page):
        self.words, self.size, self.page = words, size, page
        self.x0, self.y0, self.x1, self.y1 = box

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    def __repr__(self):
        return f"Line(p{self.page} {self.size} {self.x0}-{self.x1}: {self.text[:50]!r})"


def read_hocr(path):
    """[[Line]] per page, in reading order as the OCR gives it."""
    doc = etree.parse(path, etree.HTMLParser())
    pages = []
    for pn, page in enumerate(doc.xpath('//*[@class="ocr_page"]')):
        lines = []
        for el in page.xpath('.//*[@class="ocr_line" or @class="ocr_caption" or @class="ocr_header" '
                             'or @class="ocr_textfloat"]'):
            title = el.get("title") or ""
            m, s = BBOX.search(title), XSIZE.search(title)
            if not m:
                continue
            words = []
            for w in el.xpath('.//*[@class="ocrx_word"]'):
                t = "".join(w.itertext()).strip()
                wm = BBOX.search(w.get("title") or "")
                if t and wm:
                    words.append(Word(t, tuple(map(int, wm.groups()))))
            if words:
                lines.append(Line(words, float(s.group(1)) if s else 0.0, tuple(map(int, m.groups())), pn))
        pages.append(lines)
    return pages


def body_metrics(pages):
    """The body type size and text column, from the lines of the whole book:
    the size most words are set in, and that size's usual left and right edges."""
    sizes = Counter()
    for lines in pages:
        for l in lines:
            sizes[round(l.size)] += len(l.words)
    body = sizes.most_common(1)[0][0]
    near = [l for lines in pages for l in lines if abs(l.size - body) <= body * 0.08 and len(l.words) >= 6]
    left = statistics.median(l.x0 for l in near)
    right = statistics.median(l.x1 for l in near)
    return body, left, right


GERMAN = {"und", "der", "die", "das", "ist", "vgl", "nicht", "auch", "den", "dem", "eine", "mit",
          "zu", "von", "wird", "sich", "des", "im", "wie", "als", "bei", "oder", "s.", "aus", "dass", "dafs"}


GERMAN_MORE = {"sind", "könig", "konig", "nur", "diese", "dieser", "dessen", "sein", "seine", "seinen", "ihm",
               "ihn", "ihr", "ihre", "nach", "über", "uber", "für", "fur", "zum", "zur", "auf", "durch", "gegen",
               "werden", "wurde", "worden", "haben", "hat", "hatte", "einen", "einem", "einer", "noch", "schon",
               "sehr", "hier", "dort", "also", "bedeutet", "heisst", "heifst", "steht", "vgl", "scil", "usw",
               "eigentlich", "eig", "jmd", "etwas", "dafs", "dass", "wo", "wenn", "weil", "kann", "muss", "mufs"}


def german_word(w):
    w = w.lower().strip(".,;:")
    return w in GERMAN or w in GERMAN_MORE or bool(re.search(r"[äü]|sch|ß", w) and not re.search(r"[þðǫæœ]", w))


def german(text):
    """A line of the German notes or headings (also one where the OCR ran
    the notes' two columns together)."""
    ws = text.split()
    if len(ws) < 3:
        return False
    g = sum(german_word(w) for w in ws)
    return g >= 2 and g / len(ws) > 0.12


class TextLine:
    """A line of the edition's text: its words (margin furniture removed), and
    whether it opens a paragraph or is a line of verse (by its indent)."""
    __slots__ = ("page", "text", "indent", "width", "para", "verse")

    def __init__(self, page, text, indent, width):
        self.page, self.text, self.indent, self.width = page, text, indent, width
        self.para = 0.035 < indent < 0.18
        self.verse = indent >= 0.18

    def __repr__(self):
        flag = "V" if self.verse else ("P" if self.para else " ")
        return f"{self.page}{flag} {self.text}"


def page_column(lines):
    """(left, right) of the page's text column: the edges of its full-width lines
    (recto and verso pages have different margins)."""
    widths = sorted(l.x1 - l.x0 for l in lines)
    if not widths:
        return None
    full = [l for l in lines if l.x1 - l.x0 >= widths[-1] * 0.8 and len(l.words) >= 5]
    if len(full) < 3:
        return None
    return statistics.median(l.x0 for l in full), statistics.median(l.x1 for l in full)


def body_of_page(lines, left, right):
    """The lines of the text itself, top to bottom: without the running head
    (above the first wide gap at the top) and the notes (below a wide gap, in
    two half-width columns)."""
    lines = sorted(lines, key=lambda l: l.y0)
    if len(lines) < 3:
        return lines
    width = right - left
    gaps = [b.y0 - a.y0 for a, b in zip(lines, lines[1:])]
    # the text's line spacing: between consecutive full-width lines (the notes'
    # two columns interleave, which makes their gaps look tiny)
    wide = [g for g, a, b in zip(gaps, lines, lines[1:])
            if g > 0 and a.x1 - a.x0 > width * 0.8 and b.x1 - b.x0 > width * 0.8]
    spacing = statistics.median(wide or [g for g in gaps if g > 0] or [1])
    sizes = [l.size for l in lines if l.x1 - l.x0 > width * 0.8]
    body_size = statistics.median(sizes) if sizes else 0
    heights = [l.y1 - l.y0 for l in lines if l.x1 - l.x0 > width * 0.8]
    body_height = statistics.median(heights) if heights else 0

    def small(l):              # the notes' smaller type (the OCR's x_size is not always reliable)
        return (body_size and l.size < body_size * 0.93) or (body_height and l.y1 - l.y0 < body_height * 0.88)
    # running head: one or two lines at the top, then a wide gap
    start = 0
    for k in range(min(2, len(gaps))):
        if gaps[k] > spacing * 1.3:
            start = k + 1
            break
    # notes: after a wide gap, nearly all half-width lines (or German, or small). A
    # chapter that starts mid-page also follows a wide gap and a German heading,
    # but then the text goes on in full-width lines of the body's type.
    end = len(lines)
    for k in range(start, len(lines) - 1):
        if gaps[k] > spacing * 1.6:
            below = lines[k + 1:]
            half = sum(1 for l in below if l.x1 - l.x0 < width * 0.6 or german(l.text) or small(l))
            # the notes begin at once; a chapter heading is followed by lines of the text
            body = sum(1 for l in below[:4] if l.x1 - l.x0 > width * 0.85 and not small(l) and not german(l.text))
            if half >= len(below) * 0.6 and body < 2:
                end = k + 1
                break

    def note_like(l):
        # a line of the notes' right-hand column (verse is never indented so far),
        # or a short line in the smaller type (the left-hand column, a German heading)
        if l.x0 - left > width * 0.42:
            return True
        return bool(body_size) and l.size < body_size * 0.93 and l.x1 - l.x0 < width * 0.62
    return [l for l in lines[start:end] if not note_like(l)]


def text_lines(pages, first=0, last=None):
    """The edition's text on pages first..last, as [TextLine]."""
    _, book_left, book_right = body_metrics(pages[first:last])
    out = []
    for lines in pages[first:last]:
        col = page_column(lines) or (book_left, book_right)
        left, right = col
        width = right - left
        for l in body_of_page(lines, left, right):
            # words in the margins: line numbers (5, 10, …), references ("Nj. V.", "Eg. XL.")
            words = [w for w in l.words if w.x1 > left - width * 0.005 and w.x0 < right + width * 0.005]
            # line numbers just inside the margins (5, 10, … beside the first or last word)
            if words and re.fullmatch(r"\d{1,3}", words[0].text) and words[0].x0 < left - width * 0.01:
                words = words[1:]
            if words and re.fullmatch(r"\d{1,3}", words[-1].text) and words[-1].x1 > right + width * 0.01:
                words = words[:-1]
            if not words:
                continue
            text = " ".join(w.text for w in words)
            if german(text):
                continue
            out.append(TextLine(l.page, text, (words[0].x0 - left) / width, (words[-1].x1 - words[0].x0) / width))
    return out


def join_lines(lines):
    """Running text from lines: a word broken with a hyphen at the end of a
    line is joined to its rest on the next."""
    out = ""
    for text in lines:
        text = text.strip()
        if not text:
            continue
        if out.endswith("-") and not out.endswith(" -") and not out.endswith("--"):
            out = out[:-1] + text
        elif out:
            out += " " + text
        else:
            out = text
    return re.sub(r"\s+", " ", out)
