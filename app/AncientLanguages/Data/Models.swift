import Foundation

struct Work: Identifiable, Hashable {
    let id: Int
    let urn: String           // work-level CTS URN, e.g. urn:cts:greekLit:tlg0012.tlg001
    let author: String
    let title: String
    let kind: Kind            // verse or prose: decides the layout
    let form: String          // epic | poem | hymns | drama | dialogue | letters | history | sayings | codex
    let greekURN: String      // edition URN, e.g. …tlg0012.tlg001.perseus-grc2
    let englishURN: String
    let translator: String
    let scope: String         // "complete", or e.g. "Book 1"
    let parseSource: String   // treebank | morpheus | scriptorium | coptic-nlp | oe-forms | oshb | dcs
    let language: String      // grc | cop | lat | ang | hbo | san
    let credit: String        // edition/annotation credit (Coptic works)

    enum Kind: String { case verse, prose }

    var isDrama: Bool { form == "drama" }
    var isLatin: Bool { language == "lat" }
    var isCoptic: Bool { language == "cop" }
    var isOldEnglish: Bool { language == "ang" }
    var isHebrew: Bool { language == "hbo" }      // read right to left
    var isSanskrit: Bool { language == "san" }    // IAST, from the Digital Corpus of Sanskrit
    var isCodex: Bool { form == "codex" }   // cited by codex page and line
    var isBible: Bool { form == "bible" }   // cited by chapter and verse (5.3, shown 5:3)
    /// What the first number of a citation counts: Iliad 6.237, Hymn 2.123, codex page 17.4.
    var partUnit: String {
        switch form {
        case "codex": return "Page"
        case "hymns": return "Hymn"
        case "letters": return "Letter"
        case "speeches": return "Speech"     // Cicero's In Catilinam
        case "bible", "chapters": return "Chapter"
        case "riddles": return "Riddle"     // Old English: the Exeter Book riddles
        case "psalms": return "Psalm"       // the Paris Psalter, the psalm fragments
        case "meters": return "Meter"       // the Meters of Boethius
        case "charms": return "Charm"
        default: return "Book"
        }
    }
    /// Homer and the poets in his dialect: Autenrieth is the default lexicon.
    var isHomeric: Bool { ["Homer", "Homeric Hymns", "Hesiod"].contains(author) }
}

/// A word in the Greek text. Offsets are UTF-16 units into `Segment.text`.
struct Token: Hashable {
    let id: Int                // row id, used to look up a Coptic word's morphemes
    let segmentID: Int
    let index: Int
    let start: Int
    let end: Int
    let form: String
    let lemma: String?
    let lemmaKey: String?
    let postag: String?
    /// "treebank" (one parse, chosen in context), "morpheus" (possible parses)
    /// "scriptorium" (a Coptic bound group; its morphemes are in `morph`) or
    /// "coptic-nlp" (the same, analysed automatically).
    let source: String?
    /// Shared by the pieces of a word broken across two manuscript lines
    /// (Coptic codices), so tapping either half highlights both.
    var wordID: Int? = nil
    /// For a second aorist (εἶπον): its flashcard entry ("λέγω|aor").
    var aoristKey: String? = nil

    var range: NSRange { NSRange(location: start, length: end - start) }

    /// The same written word: this token, or another piece of it on the next line.
    func isSameWord(as other: Token) -> Bool {
        if segmentID == other.segmentID && index == other.index { return true }
        if let wordID, wordID == other.wordID { return true }
        return false
    }
}

/// One possible analysis of a word form (from Morpheus), most likely first.
struct Analysis: Hashable, Identifiable {
    let rank: Int
    let lemma: String
    let lemmaKey: String
    let parse: String
    var tag: String? = nil     // Coptic SCRIPTORIUM part-of-speech tag, for homographs
    var id: Int { rank }
}

/// Traditional reference numbers sitting inside a text, e.g. a Stephanus
/// section ("5d") at the start of a paragraph.
struct Marker: Hashable {
    let offset: Int   // UTF-16
    let unit: String  // "section", "page", "line", "para"
    let label: String
}

/// A Greek display unit: one verse line, or one paragraph/speech (or the part
/// of it inside one Stephanus section) in prose.
struct Segment: Identifiable, Hashable {
    let id: Int
    let cite: String
    let lineNumber: Int?
    let speaker: String?
    let heading: String?
    let part: String?          // I / M / F: a verse line shared between speakers
    let paragraphStart: Bool   // false: prose continuation across a section break
    let text: String
    let markers: [Marker]
    let tokens: [Token]
}

/// The alignment unit: Greek segments plus the English passage translating them.
struct Block: Identifiable, Hashable {
    let id: Int
    let citeStart: String
    let citeEnd: String
    let english: String
    let segments: [Segment]
}

/// The word the reader tapped.
struct WordSelection: Equatable {
    let token: Token
    let cite: String
    /// Set when the word is in the parallel text (the Greek beside the
    /// Vulgate, or the Latin beside the LXX/NT): it is looked up in that
    /// work's language and lexica, and can't be highlighted.
    var work: Work? = nil
    var segmentID: Int { token.segmentID }
}
