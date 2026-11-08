import Foundation

/// Turns a 9-position AGDT postag (e.g. "v2spma---") into readable grammar.
enum ParseFormatter {
    private static let partOfSpeech: [Character: String] = [
        "n": "noun", "v": "verb", "t": "participle", "a": "adjective", "d": "adverb",
        "l": "article", "g": "particle", "c": "conjunction", "r": "preposition",
        "p": "pronoun", "m": "numeral", "i": "interjection", "e": "exclamation",
        "x": "irregular",
    ]
    private static let fields: [[Character: String]] = [
        [:],
        ["1": "1st person", "2": "2nd person", "3": "3rd person"],
        ["s": "singular", "p": "plural", "d": "dual"],
        ["p": "present", "i": "imperfect", "r": "perfect", "l": "pluperfect",
         "t": "future perfect", "f": "future", "a": "aorist", "e": "past"],
        ["i": "indicative", "s": "subjunctive", "o": "optative", "n": "infinitive",
         "m": "imperative", "p": "participle", "d": "gerund", "g": "gerundive", "u": "supine"],
        ["a": "active", "p": "passive", "m": "middle", "e": "middle-passive"],
        ["m": "masculine", "f": "feminine", "n": "neuter", "c": "common"],
        ["n": "nominative", "g": "genitive", "d": "dative", "a": "accusative",
         "v": "vocative", "l": "locative", "b": "ablative", "i": "instrumental"],
        ["c": "comparative", "s": "superlative"],
    ]

    /// Coptic SCRIPTORIUM tags (e.g. "N", "APST", "ACOND_PPERS").
    private static let copticTags: [String: String] = [
        "N": "noun", "NPROP": "proper noun", "V": "verb", "VBD": "verb (with object)",
        "VSTAT": "stative verb", "VIMP": "imperative", "ADV": "adverb", "NUM": "numeral",
        "ART": "article", "PPOS": "possessive article", "PDEM": "demonstrative",
        "PINT": "interrogative pronoun", "PPERS": "personal pronoun (subject)",
        "PPERO": "personal pronoun (object)", "PPERI": "independent personal pronoun",
        "PREP": "preposition", "CONJ": "conjunction", "PTC": "particle", "NEG": "negation",
        "COP": "copula", "EXIST": "existential", "IMOD": "interrogative modifier",
        "FUT": "future auxiliary", "CREL": "relative converter", "CCIRC": "circumstantial converter",
        "CFOC": "focalising converter", "CPRET": "preterite converter",
        "APST": "past auxiliary", "AAOR": "aorist auxiliary", "ACONJ": "conjunctive",
        "ACOND": "conditional", "AJUS": "jussive", "ACAUS": "causative infinitive",
        "AOPT": "optative", "APREC": "precursive", "ALIM": "limitative", "ANY": "'not yet'",
        "ANEGPST": "negative past", "ANEGAOR": "negative aorist", "ANEGOPT": "negative optative",
        "ANEGJUS": "negative jussive", "AFUTCONJ": "future conjunctive", "FM": "foreign word",
        "UNKNOWN": "unknown",
    ]

    static func coptic(_ tag: String?) -> String {
        (tag ?? "").split(separator: "_").map { copticTags[String($0)] ?? String($0) }.joined(separator: " + ")
    }

    static func describe(_ postag: String?) -> String {
        guard let tag = postag, tag.count >= 9 else { return "" }
        let chars = Array(tag)
        var parts: [String] = []
        if let pos = partOfSpeech[chars[0]] { parts.append(pos) }
        for i in 1..<9 {
            if let value = fields[i][chars[i]], !(chars[0] == "t" && i == 4) {
                parts.append(value)
            }
        }
        return parts.joined(separator: " · ")
    }
}
