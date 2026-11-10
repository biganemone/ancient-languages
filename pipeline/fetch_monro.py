"""Fetch Monro, A Grammar of the Homeric Dialect (2nd ed., 1891), from
Dickinson College Commentaries and write it as simple TEI for build_grammar.py.

Perseus does not have Monro; DCC's edition (OCR by Bruce Robertson, corrected
by Meagan Ayer and Seth Levin) is CC BY-SA 4.0:
  https://dcc.dickinson.edu/grammar/monro/introduction-and-definitions

Each DCC page is a topic holding numbered paragraphs ("<strong>161.</strong> ..."),
grouped by chapter in the site menu. We keep that: a chapter div (head = menu
heading) > topic div (head = page title) > <div type="section" n="161">. Cross
references are links to topic pages whose text holds the numbers ("§§ 161 and
163"); each number becomes <ref target="s161">.

Raw pages are cached in <out dir>/monro_html/ so reruns don't refetch.

Usage: python fetch_monro.py <sources/grammars>     (writes monro.xml there)
"""
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import lxml.html as H
from lxml import etree

BASE = "https://dcc.dickinson.edu"
START = BASE + "/grammar/monro/introduction-and-definitions"
UA = "AncientLanguages-pipeline/1.0 (grammar build; one request per second)"
SKIP = {"editors-note", "preface", "credits-and-reuse"}


def fetch(url, cache):
    slug = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1])
    path = os.path.join(cache, re.sub(r"[^\w.-]", "_", slug) + ".html")
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
        time.sleep(1)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # DCC writes footnotes as shortcodes: "πιμπλᾶσι[fn]The μ is euphonic ...[/fn]"
    text = text.replace("[fn]", '<span class="dcc-fn">').replace("[/fn]", "</span>")
    return H.fromstring(text)


def menu(page):
    """[(chapter heading, [(topic title, url)])] in book order."""
    m = page.xpath('//ul[contains(@class,"sf-menu-grammar-monro-menu")]')[0]
    out = []
    for li in m.iter("li"):
        depth = int(next(c for c in li.get("class").split() if c.startswith("sf-depth-"))[9:])
        a = li[0]
        title = a.text_content().strip()
        href = urllib.parse.urljoin(BASE, a.get("href") or "")
        if depth == 1:
            out.append((title, []))
        elif out and "/grammar/monro/" in href:
            out[-1][1].append((title, href.split("#")[0]))
    return out


NUM_AT_START = re.compile(r"^\s*(\d+)\.\*?\s*$")


def convert(e, parent):
    """HTML inline/block content -> TEI-ish elements under parent."""
    tag = {"p": "p", "i": "emph", "em": "emph", "b": "emph", "strong": "emph",
           "table": "table", "tr": "row", "td": "cell", "th": "cell",
           "ul": "list", "ol": "list", "li": "item", "blockquote": "quote",
           "sup": "hi", "br": "lb"}.get(e.tag)
    if e.tag == "span" and e.get("class") == "dcc-fn":
        tag = "note"
    if e.tag == "a" and "/grammar/monro/" in (e.get("href") or ""):
        # "161 and 163", "§ 245, 3": every section number becomes a ref
        text = e.text_content()
        last = None
        pos = 0
        for m in re.finditer(r"\d+", text):
            seg = text[pos:m.start()]
            _append_text(parent, last, seg)
            last = etree.SubElement(parent, "ref", target="s" + m.group())
            last.text = m.group()
            pos = m.end()
        _append_text(parent, last, text[pos:])
        return last, True
    if tag is None:       # spans, tbody, thead, unknown: keep contents only
        last = None
        if e.text:
            _append_text(parent, None if not len(parent) else parent[-1], e.text)
        for c in e:
            last, _ = convert(c, parent)
            if c.tail:
                _append_text(parent, parent[-1] if len(parent) else None, c.tail)
        return (parent[-1] if len(parent) else None), True
    out = etree.SubElement(parent, tag)
    if e.tag in ("i", "em"):
        out.set("rend", "ital")
    elif e.tag in ("b", "strong"):
        out.set("rend", "bold")
    elif e.tag == "sup":
        out.set("rend", "sup")
    if e.text:
        out.text = e.text
    for c in e:
        convert(c, out)
        if c.tail:
            _append_text(out, out[-1] if len(out) else None, c.tail)
    return out, False


def _append_text(parent, last, text):
    if not text:
        return
    if last is not None and last.getparent() is parent:
        last.tail = (last.tail or "") + text
    elif len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def lead(p):
    """A paragraph's opening (bold number, anchor id), past empty anchors:
    <p><a class="ck-anchor" id="32"></a><strong>32.</strong> ..."""
    anchor = None
    text = (p.text or "").strip()
    for c in p:
        if text:
            return None, None
        if c.tag == "a" and not c.text_content().strip():
            anchor = c.get("id")
            text = (c.tail or "").strip()
            continue
        if c.tag in ("strong", "b"):
            m = NUM_AT_START.match(c.text_content())
            return (c, anchor) if m else (None, None)
        return None, None
    return None, None


def section_number(p):
    """A paragraph that opens a section starts with <strong>N.</strong>."""
    first, _ = lead(p)
    return NUM_AT_START.match(first.text_content()).group(1) if first is not None else None


def opens_section(p, n, current, seen, first_on_page):
    """Not every bold "3." is a section: lists inside a section number their
    items too. A section number is new, and opens the page, carries the
    matching anchor, or follows the section before it."""
    if n is None or n in seen:
        return False
    _, anchor = lead(p)
    return first_on_page or anchor == n or (current is not None and int(n) > int(current))


def main(out_dir):
    cache = os.path.join(out_dir, "monro_html")
    os.makedirs(cache, exist_ok=True)
    chapters = menu(fetch(START, cache))
    tei = etree.Element("TEI.2")
    body = etree.SubElement(etree.SubElement(tei, "text"), "body")
    count = 0
    seen = set()
    last_section = None
    for chapter, topics in chapters:
        topics = [t for t in topics if t[1].rsplit("/", 1)[-1] not in SKIP]
        if not topics:
            continue
        cdiv = etree.SubElement(body, "div1", type="chapter")
        etree.SubElement(cdiv, "head").text = chapter
        for title, url in topics:
            page = fetch(url, cache)
            # the page has several body fields (site blocks); the text is the one
            # with the numbered paragraphs
            bodies = page.xpath('//div[contains(@class,"field--name-body")]')
            content = sorted(bodies, key=lambda b: -sum(1 for p in b.iter("p") if section_number(p)))[:1]
            if not content:
                print("no body:", url, file=sys.stderr)
                continue
            tdiv = etree.SubElement(cdiv, "div2", type="topic")
            etree.SubElement(tdiv, "head").text = title
            current = None
            first_on_page = True
            topic_has_section = False
            for block in content[0]:
                if not isinstance(block.tag, str):
                    continue
                n = section_number(block) if block.tag == "p" else None
                if opens_section(block, n, current, seen, first_on_page):
                    seen.add(n)
                    current = n
                    section = etree.SubElement(tdiv, "div3", type="section", n=n)
                    block = H.fromstring(H.tostring(block))   # a copy we can trim
                    first, _ = lead(block)
                    for a in [c for c in block if c is not first and c.tag == "a" and c.getnext() is first]:
                        block.remove(a)
                    block.text = first.tail
                    block.remove(first)
                    # heading: a run-in title ("<em>Vocative</em>. A noun ..."), else the
                    # topic's title for its first section
                    lead_in = block[0] if len(block) and not (block.text or "").strip() else None
                    if lead_in is not None and lead_in.tag in ("em", "i") and (lead_in.tail or "").lstrip().startswith("."):
                        section.set("heading", lead_in.text_content().strip())
                    elif not topic_has_section:
                        section.set("heading", title)
                    topic_has_section = True
                    count += 1
                if block.tag == "p" or len(block) or (block.text or "").strip():
                    first_on_page = False
                if current is None and last_section is None:
                    convert(block, tdiv)          # before the first section of the book
                elif current is None:
                    convert(block, last_section)  # a page that continues the section before it
                else:
                    convert(block, section)
            if current is not None:
                last_section = section
    etree.ElementTree(tei).write(os.path.join(out_dir, "monro.xml"), encoding="utf-8",
                                 xml_declaration=True, pretty_print=True)
    print(f"monro.xml: {count} sections", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
