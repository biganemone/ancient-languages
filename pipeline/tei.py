"""Turn TEI elements into plain text plus positioned markers.

walk() flattens an element into events; assemble() collapses whitespace and
returns (text, markers) where markers are (offset, unit, n) tuples, e.g.
(0, 'section', '2a') for a Stephanus section or (212, 'line', '5') for a
line milestone inside an English prose translation.
"""
import re
from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"


def local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def walk(el, events, skip=("note", "label", "bibl", "head")):
    name = local(el.tag)
    if name == "milestone":
        events.append(("ms", (el.get("unit") or "").lower(), el.get("n")))
    elif name not in skip and isinstance(el.tag, str):
        if el.text:
            events.append(("text", el.text))
        for child in el:
            walk(child, events, skip)
        if name == "p":
            events.append(("para",))
    if el.tail:
        events.append(("text", el.tail))


def element_events(el, skip=("note", "label", "bibl", "head")):
    """Events for el's own content (not its tail)."""
    events = []
    name = local(el.tag)
    if el.text:
        events.append(("text", el.text))
    for child in el:
        walk(child, events, skip)
    return events


def assemble(events):
    out, markers = "", []
    for ev in events:
        if ev[0] == "text":
            t = re.sub(r"\s+", " ", ev[1])
            if (not out or out.endswith((" ", "\n"))) and t.startswith(" "):
                t = t[1:]
            out += t
        elif ev[0] == "para":
            out = out.rstrip(" ")
            if out and not out.endswith("\n\n"):
                out += "\n\n"
        elif ev[0] == "ms":
            markers.append([len(out), ev[1], ev[2]])
    # trim, shifting markers
    lead = len(out) - len(out.lstrip())
    out = out.strip()
    markers = [[max(0, min(len(out), o - lead)), u, n] for o, u, n in markers]
    return out, markers


def parse(path):
    parser = etree.XMLParser(recover=True, remove_comments=True)
    return etree.parse(path, parser).getroot()


def find_all(root, name):
    return [e for e in root.iter() if local(e.tag) == name]
