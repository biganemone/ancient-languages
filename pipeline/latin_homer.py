"""The Latin Homer: the word-for-word Latin version of the Didot edition
(Homeri Carmina et Cycli Epici Reliquiae, Graece et Latine, Paris 1837-38),
as transcribed by Project Gutenberg (#52692 Ilias, #52693 Odyssea; the files
are kept in data/didot_latin/). Read by build_latin.py.

The Latin was printed line for line under the Greek, numbered every fifth line,
and the numbering agrees with the Greek book by book (Il. 1: 611 lines ... Od.
24: 548). Each Latin work takes its blocks from the Greek work already in
texts.db (Murray's five-line blocks, with Murray's English), so that each Latin
block has the same citation as a Greek one; build_latin.py records the pairs
in the parallel map, which lets the reader show the Latin beside (or under)
the Greek and the reverse. Lines the Greek edition (Monro-Allen) leaves out
(Il. 9.458-61 and a few others) go into the block whose range they fall in.

In the e-text, italics (_x_) mark the translator's supplements; they are kept
as plain text. Hyphens join the Latin words that render one Greek word
("prædam-diripiendam") and are kept; the tokenizer reads the parts as words.
"""
import gzip
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "didot_latin")
HEAD = re.compile(r"^\s+(Iliadis|Odysseæ|Odysseae|Odyssea)\s+([IVXLC]+)\.")
CREDIT = ("Latin: the word-for-word version printed with the Greek in the Didot edition (Homeri Carmina, "
          "Paris, 1837-38), from the Project Gutenberg transcription (public domain); English: A. T. Murray, "
          "from the Perseus Digital Library (CC BY-SA).")

WORKS = [
    dict(file="pg52692.txt.gz", greek_urn="urn:cts:greekLit:tlg0012.tlg001", urn="urn:cts:latinLit:homer.ilias_didot",
         title="Ilias (versio Latina)"),
    dict(file="pg52693.txt.gz", greek_urn="urn:cts:greekLit:tlg0012.tlg002",
         urn="urn:cts:latinLit:homer.odyssea_didot", title="Odyssea (versio Latina)"),
    dict(file="pg52691.txt.gz", greek_urn="urn:cts:greekLit:tlg0013", urn="urn:cts:latinLit:homer.hymni_didot",
         title="Hymni Homerici (versio Latina)", hymns=True),
]

# Didot's (Wolf's) order of the Hymns -> the standard numbering of the Greek work
# (I In Apollinem = 3, IV In Cererem = 2, XXVI In Eundem = 1, the Dionysus fragment; ...)
HYMN_NUMBER = {1: 3, 2: 4, 3: 5, 4: 2, **{n: n + 1 for n in range(5, 25)}, 25: 26, 26: 1,
               **{n: n for n in range(27, 34)}}
HYMN_HEAD = re.compile(r"^\s{10,}([IVXL]+)\.\s+(IN .*)\.$")


def roman(s):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    return sum(-v[c] if i + 1 < len(s) and v[s[i + 1]] > v[c] else v[c] for i, c in enumerate(s))


def read(path):
    """-> {book: [dict(n, text, para)]}; checks the printed line numbers."""
    books, cur, intext, para = {}, None, False, False
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line.startswith("*** END"):
                break
            m = HEAD.match(line)
            if m:
                cur = books.setdefault(roman(m.group(2)), [])
                intext = False
                continue
            if cur is None:
                continue
            if line.strip() == "TEXT:":
                intext, para = True, True
                continue
            if not intext:
                continue
            if re.match(r"^\s*\[TR\d+\]", line):        # the transcriber's notes after each book
                intext = False
                continue
            if not line.strip():
                para = True
                continue
            num, rest = line[:5].strip(), line[5:]
            if num and not num.isdigit():
                num, rest = "", line
            col = 5 + len(rest) - len(rest.lstrip()) if num else len(line) - len(line.lstrip())
            text = re.sub(r"\[TR\d+\]", "", rest.strip())
            text = re.sub(r"_([^_]*)_", r"\1", text)
            if col >= 10 and cur and not num:            # a long line wrapped in the e-text
                cur[-1]["text"] += " " + text
                continue
            n = len(cur) + 1
            if num and int(num) != n:
                raise ValueError(f"{path}: book line {n} printed as {num}")
            cur.append(dict(n=n, text=text, para=para or col == 8))
            para = False
    return books


def read_hymns(path):
    """-> {standard hymn number: [dict(n, text, para)]}, and their Latin titles."""
    hymns, titles, cur, para, active = {}, {}, None, False, False
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if "HYMNI VEL EXORDIA" in line:
                active = True
                continue
            if not active:
                continue
            if line.strip() == "EPIGRAMMATA." and hymns:
                break
            m = HYMN_HEAD.match(line)
            if m:
                n = HYMN_NUMBER[roman(m.group(1))]
                cur = hymns.setdefault(n, [])
                titles[n] = m.group(2).title().replace("Et ", "et ").replace("In Eundem", "In Bacchum")
                para = True
                continue
            if cur is None or line.strip() in ("***", ""):
                para = para or not line.strip()
                continue
            if re.match(r"^\s*\[TR\d+\]", line):
                continue
            num, rest = line[:5].strip(), line[5:]
            if num and not num.isdigit():
                continue                      # the transcriber's notes run on over several lines
            col = 5 + len(rest) - len(rest.lstrip()) if num else len(line) - len(line.lstrip())
            text = re.sub(r"_([^_]*)_", r"\1", re.sub(r"\[TR\d+\]", "", rest.strip()))
            if col >= 10 and cur and not num:
                cur[-1]["text"] += " " + text
                continue
            n = len(cur) + 1
            if num and int(num) != n:
                raise ValueError(f"{path}: hymn line {n} printed as {num}")
            cur.append(dict(n=n, text=text, para=para or col == 8))
            para = False
    return hymns, titles


def blocks_for(db, w):
    """Latin blocks shaped like the Greek work's: [(greek block id, block dict)]."""
    gid = db.execute("SELECT id FROM work WHERE urn = ?", (w["greek_urn"],)).fetchone()
    if not gid:
        return []
    greek = db.execute("SELECT id, cite_start, cite_end, english FROM block WHERE work_id = ? ORDER BY seq",
                       (gid[0],)).fetchall()
    if w.get("hymns"):
        books, titles = read_hymns(os.path.join(DATA, w["file"]))
    else:
        books, titles = read(os.path.join(DATA, w["file"])), {}

    def num(cite):
        b, _, l = cite.partition(".")
        return int(b), int(re.sub(r"\D.*", "", l) or 0)

    out = [(bid, dict(cite_start=cs, cite_end=ce, english=en, segments=[])) for bid, cs, ce, en in greek]
    starts = [num(cs) for _, cs, _, _ in greek]
    j = 0
    for book in sorted(books):
        for i, line in enumerate(books[book]):
            key = (book, line["n"])
            while j + 1 < len(starts) and starts[j + 1] <= key:
                j += 1
            out[j][1]["segments"].append(dict(
                cite=f"{book}.{line['n']}", line_n=line["n"],
                heading=(f"Hymn {book} · {titles[book]}" if titles else f"Book {book}") if i == 0 else None,
                para=line["para"], text=line["text"], markers=[]))
    return [(bid, b) for bid, b in out if b["segments"]]
