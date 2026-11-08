"""(How data/marcus_aurelius_long.xml was made, from Gutenberg #15877; kept for reference.)

George Long's Marcus Aurelius (Gutenberg #15877) -> a minimal TEI file
with book and chapter divs, matching the Greek's book.chapter numbering."""
import re, sys, html
t = open(sys.argv[1], encoding="utf-8").read().replace("\r\n", "\n")
body = t[t.index("THE THOUGHTS\n\nOF\n\nMARCUS AURELIUS ANTONIUS."):t.index("\nINDEXES.")]
heads = [(m.start(), m.end()) for m in re.finditer(r"\n\n([IVX]+)\.\n\n", body)]
books = []
for i, (a, b) in enumerate(heads):
    text = body[b:heads[i + 1][0] if i + 1 < len(heads) else len(body)]
    paras = re.split(r"\n\s*\n", text)
    kept = []
    for p in paras:
        if re.match(r"\s{2,}\[[A-Z]+\]", p) or re.match(r"^\s{4}", p):   # footnotes (indented)
            continue
        p = re.sub(r"\[[A-Z]{1,2}\]", "", p)                                # footnote references
        p = " ".join(p.split())
        if p:
            kept.append(p)
    chapters, cur = {}, 1
    for p in kept:
        m = re.match(r"(\d+)\.\s+(.*)", p)
        if m and int(m.group(1)) == cur + 1:
            cur = int(m.group(1))
            p = m.group(2)
        chapters[cur] = (chapters.get(cur, "") + "\n\n" + p).strip()
    books.append(chapters)
out = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div type="translation">']
for bi, ch in enumerate(books, 1):
    out.append(f'<div type="textpart" subtype="book" n="{bi}">')
    for n, txt in ch.items():
        ps = "".join(f"<p>{html.escape(x, quote=False)}</p>" for x in txt.split("\n\n"))
        out.append(f'<div type="textpart" subtype="chapter" n="{n}">{ps}</div>')
    out.append("</div>")
out.append("</div></body></text></TEI>")
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
print([len(b) for b in books])
