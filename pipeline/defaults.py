"""The texts the app ships with (Adam's default list, app/specs/text and
languages.md); everything else in the full build is for downloadable
modules. All dictionaries ship (decided Nov 7, 2026).

export_module.py --defaults selects these from texts_app.db."""

URNS = [
    "urn:cts:greekLit:tlg0012.tlg001", "urn:cts:greekLit:tlg0012.tlg002",       # Iliad, Odyssey
    "urn:cts:greekLit:tlg0059.tlg001", "urn:cts:greekLit:tlg0059.tlg002",       # Euthyphro, Apology
    "urn:cts:greekLit:tlg0059.tlg003",                                          # Crito
    "urn:cts:greekLit:tlg0011.tlg002",                                          # Antigone
    "urn:cts:copticLit:nh.thomas",                                              # Gospel of Thomas
    "urn:cts:angLit:anon.beowulf",                                              # Beowulf
]
AUTHORS = ["New Testament", "Herodotus", "Marcus Aurelius"]
LANGUAGES = ["lat", "hbo", "san"]          # all the Latin, the Hebrew Bible, the Gītā and Upanishads
