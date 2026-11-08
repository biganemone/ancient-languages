"""The Anglo-Saxon Poetic Records (ed. Krapp & Dobbie, 1931–53) in Greg
Hidley's electronic text (Oxford Text Archive; sacred-texts.com's "Complete
Corpus of Anglo-Saxon Poetry"), as collected in cltk/old_english_text_sacred_texts
(html/): one HTML page per poem, the line number every fifth line, the
half-lines separated by non-breaking spaces, editorial letters in <strong>.

read_corpus() -> [dict(group, work, title, form, part, lines=[(n, text)])]:
the poems grouped as the manuscripts (and ASPR volumes) group them; the
riddles, the Paris Psalter, the Meters of Boethius, the psalm fragments and
the metrical charms each become one work cited by part (Riddle 5.3, Psalm
100.12). Beowulf is left out (the app's comes from Klaeber's edition).
"""
import glob
import html
import os
import re

CAESURA = "  "

JUNIUS = ["Genesis A, B", "Exodus", "Daniel", "Christ and Satan"]
VERCELLI = ["Andreas", "The Fates of the Apostles", "Soul and Body I", "Homiletic Fragment I",
            "Dream of the Rood", "Elene"]
TITLE_FIXES = {"Metrical Preface to the Pastoral Car": "Metrical Preface to the Pastoral Care",
               "The Mologium": "The Menologium", "Dream of the Rood": "The Dream of the Rood",
               "Genesis A, B": "Genesis", "Christ A, B, C": "Christ", "Guthlac A, B": "Guthlac",
               "Unknown": "A Fragment"}
# ASPR's order for the Junius and Vercelli books and the minor poems (vol. VI)
ORDER = ["Genesis", "Exodus", "Daniel", "Christ and Satan",
         "Andreas", "The Fates of the Apostles", "Soul and Body I", "Homiletic Fragment I", "The Dream of the Rood",
         "Elene", "Judith",
         "The Battle of Finnsburh", "Waldere A", "Waldere B", "The Battle of Maldon", "The Battle of Brunanburh",
         "The Capture of the Five Boroughs", "The Coronation of Edgar", "The Death of Edward", "Durham",
         "The Rune Poem", "Solomon and Saturn", "The Menologium", "Maxims II", "A Proverb from Winfrid's Time",
         "The Judgment Day II", "An Exhortation to Christian Living", "A Summons to Prayer", "The Lord's Prayer II",
         "The Gloria I", "The Lord's Prayer III", "The Creed", "Psalm Fragments", "The Kentish Hymn", "Psalm 50",
         "The Gloria II", "A Prayer", "Thureth", "Aldhelm", "The Seasons for Fasting",
         "Caedmon's Hymn: Northumbrian Version", "Caedmon's Hymn: West Saxon Version",
         "Bede's Death Song: Northumbrian Version", "Bede's Death Song: West Saxon Version",
         "Bede's Death Song: The Hague Version", "The Leiden Riddle", "Latin-English Proverbs",
         "Metrical Preface to the Pastoral Care", "Metrical Epilogue to the Pastoral Care",
         "The Metrical Preface to Waerferth's Translation of Gregory's Dialogues",
         "The Metrical Epilogue to MS 41, Corpus Christi College, Cambridge", "A Fragment", "Metrical Charms"]
GROUP_ORDER = ["Junius Manuscript", "Vercelli Book", "Exeter Book", "Beowulf Manuscript",
               "Paris Psalter", "Meters of Boethius", "Minor Poems"]


def page_lines(path):
    s = open(path, encoding="latin-1").read()
    title = re.search(r"<h1>(.*?)</h1>", s, re.S | re.I)
    title = html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else ""
    body = s[s.lower().find("<dl"):] if "<dl" in s.lower() else s
    body = body[:body.lower().rfind("</dl>")] if "</dl>" in body.lower() else body
    lines, n = [], 1
    for m in re.finditer(r"<dt>(.*?)</dt>|<dd>(.*?)</dd>", body, re.S | re.I):
        if m.group(1) is not None:
            num = re.sub(r"\D", "", m.group(1))
            if num:
                n = int(num)
            continue
        for raw in re.split(r"<br\s*/?>", m.group(2), flags=re.I):
            if not raw.strip():
                continue
            t = raw.replace("&nbsp;", " ")
            t = re.sub(r"<[^>]+>", "", t)
            t = html.unescape(t)
            t = re.sub(r"\s* [  ]*\s*", CAESURA, t)
            t = re.sub(r"[ \t\r\n]+", " ", t).strip().strip(CAESURA).strip()
            if t and not ("<text>" in t or re.match(r"^\d+\w*\.\s+MS\b", t)):   # (editor's notes)
                lines.append((n, t))
                n += 1
    return title, lines


def read_corpus(html_dir):
    poems, seen = [], set()
    for path in sorted(glob.glob(os.path.join(html_dir, "**", "*.htm*"), recursive=True)):
        rel = os.path.relpath(path, html_dir)
        top = rel.split(os.sep)[0]
        title, lines = page_lines(path)
        if not lines or title in seen or title == "Beowulf":
            continue
        seen.add(title)
        part, form, work = None, "poem", None
        if top == "exeter_book":
            group = "Exeter Book"
            m = re.match(r"Riddles? (\d+\w*)", title)
            if m:
                part, form, work = m.group(1), "riddles", "Riddles"
        elif top == "Cotton-Vitellius-A-XV":
            group = "Beowulf Manuscript"
        elif top == "Paris_Psalter":
            group, form, work = "Paris Psalter", "psalms", "The Paris Psalter"
            part = re.search(r"(\d+)\s*$", title).group(1)
        elif top == "meters_of_boethius":
            group, form, work = "Meters of Boethius", "meters", "The Meters of Boethius"
            m = re.search(r"Meter (\d+)", title)
            part = m.group(1) if m else "Proem"
        elif top == "Fragments_of_Psalms":
            group, form, work = "Minor Poems", "psalms", "Psalm Fragments"
            part = re.search(r"(\d+)\s*$", title).group(1)
        elif top == "Metrical_Charms":
            group, form, work = "Minor Poems", "charms", "Metrical Charms"
            m = re.search(r"Charm (\d+)", title)
            part = m.group(1) if m else str(len([p for p in poems if p["work"] == "Metrical Charms"]) + 1)
        elif title in JUNIUS:
            group = "Junius Manuscript"
        elif title in VERCELLI:
            group = "Vercelli Book"
        else:
            group = "Minor Poems"
        title = TITLE_FIXES.get(title, title)
        poems.append(dict(group=group, work=work or title, title=title, form=form, part=part, lines=lines,
                          path=rel))
    # order: the manuscripts' (ASPR's) order; parts numerically
    def sort_key(p):
        num = re.match(r"(\d+)(\w*)", p["part"] or "")
        part = (int(num.group(1)), num.group(2)) if num else (-1, p["part"] or "")
        title = p["work"]
        if title in ORDER:
            pos = ORDER.index(title)
        else:
            code = re.search(r"a\d\d_(\d\d)", p["path"])
            pos = 100 + (int(code.group(1)) if code else 99)
        return (GROUP_ORDER.index(p["group"]), pos, title, part)
    poems.sort(key=sort_key)
    return poems
