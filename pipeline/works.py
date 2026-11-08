"""The works the app ships, and how to read each one.

kind:     verse (one row per line) or prose (one row per paragraph/speech)
form:     epic | drama | dialogue | history (book.chapter.section) | sections (book.section) …
blocks:   what an English block corresponds to:
            line5   - Murray's 5-line milestones (Homer)
            card    - Perseus "cards" (Sophocles: ~10-30 lines, at speech breaks)
            section - Stephanus sections (Plato)
            chapter - chapters (Herodotus, Thucydides: book / chapter / section);
                      with section_blocks=True a block per section (the English
                      has the same sections)
            english - the English translation's own chunks, each starting at a
                      numbered Greek section (Josephus: Whiston's sections over Niese's)
treebank: AGDT v2.1 file if the work is treebanked (context-correct parses);
          otherwise Morpheus supplies possible parses.
gorman:   files from Vanessa Gorman's dependency treebanks (CC BY-SA 4.0) covering
          part of the work; aligned book by book, Morpheus for the rest.
books:    restrict to these books (None = whole work)
"""

HOMER = dict(author="Homer", kind="verse", form="epic", blocks="line5", dialect="epic")
SOPHOCLES = dict(author="Sophocles", kind="verse", form="drama", blocks="card", dialect="attic",
                 translator="R. C. Jebb")
PLATO = dict(author="Plato", kind="prose", form="dialogue", blocks="section", dialect="attic")
AESCHYLUS = dict(author="Aeschylus", kind="verse", form="drama", blocks="card", dialect="attic",
                 translator="H. W. Smyth")
# Hesiod: no book divisions, so the treebank is aligned to the whole poem ("poem").
HESIOD = dict(author="Hesiod", kind="verse", form="poem", blocks="card", dialect="epic",
              greek="perseus-grc2", english="perseus-eng2", translator="H. G. Evelyn-White")

# The 33 Homeric Hymns are read as one work, each hymn a part ("2.123" = Hymn 2, line 123).
HYMN_TITLES = [
    "To Dionysus", "To Demeter", "To Apollo", "To Hermes", "To Aphrodite", "To Aphrodite",
    "To Dionysus", "To Ares", "To Artemis", "To Aphrodite", "To Athena", "To Hera", "To Demeter",
    "To the Mother of the Gods", "To Heracles", "To Asclepius", "To the Dioscuri", "To Hermes",
    "To Pan", "To Hephaestus", "To Apollo", "To Poseidon", "To Zeus", "To Hestia",
    "To the Muses and Apollo", "To Dionysus", "To Artemis", "To Athena", "To Hestia", "To Earth",
    "To Helios", "To Selene", "To the Dioscuri",
]
HYMNS = dict(author="Homer", title="Homeric Hymns", work="tlg0013", kind="verse", form="hymns",
             blocks="card", dialect="epic", greek="perseus-grc2", english="perseus-eng2",
             translator="H. G. Evelyn-White",
             parts=[dict(n=str(i), work=f"tlg0013.tlg{i:03d}", heading=f"Hymn {i} · {t}",
                         treebank="tlg0013.tlg002.perseus-grc1.tb.xml" if i == 2 else None)
                    for i, t in enumerate(HYMN_TITLES, 1)])

WORKS = [
    dict(HOMER, work="tlg0012.tlg001", title="Iliad", greek="perseus-grc2", english="perseus-eng3",
         translator="A. T. Murray", treebank="tlg0012.tlg001.perseus-grc1.tb.xml"),
    dict(HOMER, work="tlg0012.tlg002", title="Odyssey", greek="perseus-grc2", english="perseus-eng3",
         translator="A. T. Murray", treebank="tlg0012.tlg002.perseus-grc1.tb.xml"),
    HYMNS,
    dict(HESIOD, work="tlg0020.tlg001", title="Theogony", treebank="tlg0020.tlg001.perseus-grc1.tb.xml"),
    dict(HESIOD, work="tlg0020.tlg002", title="Works and Days", treebank="tlg0020.tlg002.perseus-grc1.tb.xml"),
    dict(HESIOD, work="tlg0020.tlg003", title="Shield of Heracles", treebank="tlg0020.tlg003.perseus-grc1.tb.xml"),

    dict(SOPHOCLES, work="tlg0011.tlg002", title="Antigone", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0011.tlg002.perseus-grc2.tb.xml"),
    dict(SOPHOCLES, work="tlg0011.tlg004", title="Oedipus Tyrannus", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0011.tlg004.perseus-grc1.tb.xml"),
    dict(SOPHOCLES, work="tlg0011.tlg007", title="Oedipus at Colonus", greek="perseus-grc2", english="perseus-eng2"),
    dict(SOPHOCLES, work="tlg0011.tlg003", title="Ajax", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0011.tlg003.perseus-grc1.tb.xml"),
    dict(SOPHOCLES, work="tlg0011.tlg005", title="Electra", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0011.tlg005.perseus-grc2.tb.xml"),
    dict(SOPHOCLES, work="tlg0011.tlg001", title="Trachiniae", greek="perseus-grc2", english="perseus-eng3",
         treebank="tlg0011.tlg001.perseus-grc2.tb.xml"),
    dict(SOPHOCLES, work="tlg0011.tlg006", title="Philoctetes", greek="perseus-grc2", english="perseus-eng2"),

    dict(PLATO, work="tlg0059.tlg001", title="Euthyphro", greek="perseus-grc1", english="perseus-eng2",
         translator="H. N. Fowler", treebank="tlg0059.tlg001.perseus-grc1.tb.xml"),
    dict(PLATO, work="tlg0059.tlg002", title="Apology", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler",
         gorman=["plato apology.xml"]),
    dict(PLATO, work="tlg0059.tlg003", title="Crito", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler",
         gorman=["Plato_Crito_Travis_Kahl.xml"]),
    dict(PLATO, work="tlg0059.tlg004", title="Phaedo", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg005", title="Cratylus", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg006", title="Theaetetus", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg007", title="Sophist", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg008", title="Statesman", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg009", title="Parmenides", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg010", title="Philebus", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg011", title="Symposium", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg012", title="Phaedrus", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg013", title="Alcibiades I", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg014", title="Alcibiades II", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg015", title="Hipparchus", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg016", title="Lovers", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg017", title="Theages", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg018", title="Charmides", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg019", title="Laches", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg020", title="Lysis", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg021", title="Euthydemus", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg022", title="Protagoras", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg023", title="Gorgias", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg024", title="Meno", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg025", title="Greater Hippias", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg026", title="Lesser Hippias", greek="perseus-grc2", english="perseus-eng2",
         translator="H. N. Fowler"),
    dict(PLATO, work="tlg0059.tlg027", title="Ion", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg028", title="Menexenus", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury"),
    dict(PLATO, work="tlg0059.tlg029", title="Cleitophon", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury"),
    dict(PLATO, work="tlg0059.tlg030", title="Republic", greek="perseus-grc2", english="perseus-eng2",
         translator="Paul Shorey"),
    dict(PLATO, work="tlg0059.tlg031", title="Timaeus", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury"),
    dict(PLATO, work="tlg0059.tlg032", title="Critias", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury"),
    dict(PLATO, work="tlg0059.tlg033", title="Minos", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg034", title="Laws", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury"),
    dict(PLATO, work="tlg0059.tlg035", title="Epinomis", greek="perseus-grc2", english="perseus-eng2",
         translator="W. R. M. Lamb"),
    dict(PLATO, work="tlg0059.tlg036", title="Letters", greek="perseus-grc2", english="perseus-eng2",
         translator="R. G. Bury", form="letters", unit="Letter"),

    dict(AESCHYLUS, work="tlg0085.tlg001", title="Suppliant Women", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg001.perseus-grc2.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg002", title="Persians", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg002.perseus-grc2.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg003", title="Prometheus Bound", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg003.perseus-grc2.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg004", title="Seven Against Thebes", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg004.perseus-grc2.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg005", title="Agamemnon", greek="perseus-grc2", english="perseus-eng3",
         treebank="tlg0085.tlg005.perseus-grc1.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg006", title="Libation Bearers", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg006.perseus-grc2.tb.xml"),
    dict(AESCHYLUS, work="tlg0085.tlg007", title="Eumenides", greek="perseus-grc2", english="perseus-eng2",
         treebank="tlg0085.tlg007.perseus-grc1.tb.xml"),

    dict(author="Herodotus", work="tlg0016.tlg001", title="Histories", kind="prose", form="history",
         blocks="chapter", dialect="ionic", greek="perseus-grc2", english="perseus-eng2",
         translator="A. D. Godley", treebank="tlg0016.tlg001.perseus-grc1.1.tb.xml", treebank_book="1", section_blocks=True),
    dict(author="Thucydides", work="tlg0003.tlg001", title="History of the Peloponnesian War", kind="prose",
         form="history", blocks="chapter", dialect="attic", greek="perseus-grc2", english="perseus-eng6",
         translator="Richard Crawley", run_on_english=True, section_blocks=True,
         gorman=[f"thuc 1 {r}.xml" for r in ("1-20 bu5", "21-40 bu4", "41-60 bu3", "61-80 bu3", "81-100 bu2",
                                              "101-120 bu2", "121-146 bu3")]
                + ["thuc 3.1-20 bu1.xml", "thuc 3.21-40 bu1.xml"]),
    dict(author="Marcus Aurelius", work="tlg0562.tlg001", title="Meditations", kind="prose", form="history",
         blocks="chapter", dialect="attic", greek="perseus-grc2", english="long-eng",
         english_file="data/marcus_aurelius_long.xml", translator="George Long"),
    dict(author="Josephus", work="tlg0526.tlg004", title="The Jewish War", kind="prose", form="sections",
         blocks="english", dialect="attic", greek="perseus-grc2", english="perseus-eng2",
         translator="William Whiston",
         gorman=[f"josephus BJ 1.{r}.xml" for r in ("1-2 bu1", "3-5 bu2", "6-10 bu1", "11-15 bu1",
                                                     "16-20 bu1", "21-25 bu1")]),
]


def source_files(data_dir):
    """Paths (relative to canonical-greekLit) of every TEI file needed."""
    out = []
    for w in WORKS:
        for part in w.get("parts") or [w]:
            group, work = part["work"].split(".")
            for which in ("greek", "english"):
                if w.get(f"{which}_file"):
                    continue
                out.append(f"data/{group}/{work}/{part['work']}.{w[which]}.xml")
    return out


def gorman_files():
    return sorted({f for w in WORKS for f in w.get("gorman") or []})


def treebank_files():
    return sorted({p["treebank"] for w in WORKS for p in (w.get("parts") or [w]) if p.get("treebank")})
