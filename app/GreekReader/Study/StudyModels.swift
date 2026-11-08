import Foundation

/// Which way a card asks: show the Greek (or Coptic) and recall the meaning,
/// or show the meaning and recall the word.
enum CardDirection: String, Codable, CaseIterable {
    case toEnglish = "gr"
    case fromEnglish = "en"
}

/// How a deck chooses which new words to introduce next.
enum NewWordOrder: String, Codable, CaseIterable, Identifiable {
    case textOrder, frequency, balanced
    var id: String { rawValue }
    var label: String {
        switch self {
        case .textOrder: return "In order of the text"
        case .frequency: return "Most common first"
        case .balanced: return "Balanced"
        }
    }
}

/// Part of a deck's reading: a whole author, a whole work, or a range of a
/// work's books (hymns, codex pages, …), inclusive.
struct DeckSource: Codable, Hashable, Identifiable {
    var author: String?          // all works by this author (e.g. "Homer")
    var workURN: String?
    var fromPart: String?        // part keys ("1", "6"); nil = from the start / to the end
    var toPart: String?

    var id: String { "\(author ?? "")|\(workURN ?? "")|\(fromPart ?? "")|\(toPart ?? "")" }
}

/// A set of flashcards drawn from some texts. What you remember about a word
/// is kept once, for the whole app; a deck decides which words to introduce
/// and which due cards to show.
struct Deck: Codable, Identifiable, Hashable {
    var id = UUID()
    var name: String
    var sources: [DeckSource] = []
    var bothDirections = false
    var order: NewWordOrder = .balanced
    /// For `.balanced`: 0 = purely in text order, 1 = purely by frequency.
    var balance = 0.7
    var newPerDay = 10
    var maxPerDay = 100            // includes the new cards
    var skipFunctionWords = true
    var separateAorists = true     // εἶπον as a card of its own, not under λέγω
    var allForms = false           // every inflected form a card of its own
    /// The deck "My words": words added from the reader, and highlighted words.
    var isMyWords = false
    var includeHighlights = true
    var created = Date()

    /// What the cards depend on: when this changes, the word list is rebuilt.
    var vocabularySignature: String {
        "\(sources.map(\.id).joined(separator: ";"))|\(separateAorists)|\(allForms)|\(isMyWords)|\(includeHighlights)"
    }
}

/// One word (or aorist, or form) a deck can teach.
struct VocabEntry: Identifiable, Hashable {
    enum Kind: Int { case word = 0, aorist = 1, form = 2 }
    let key: String                // lemma key; "λέγω|aor"; "form:ἄειδε"
    let headword: String
    let gloss: String?
    let kind: Kind
    let baseHeadword: String?      // aorists and forms: the dictionary word (λέγω)
    let lookupKey: String          // lemma key to open in the lexicon
    let isFunctionWord: Bool
    let coptic: Bool
    var count: Int
    var firstToken: Int            // where the deck first meets it (for the example line)
    var position: Int              // order of first appearance across the deck's texts

    var id: String { key }

    func cardKey(_ d: CardDirection) -> String { "\(key)#\(d.rawValue)" }
}

/// The schedule of one card (an entry in one direction).
struct CardState: Codable, Hashable {
    var memory: FSRS.Memory?
    var due: Date
    var lastReview: Date?
    var reps = 0
    var lapses = 0
    var introduced: Date
    /// The token the card was introduced from (for its example line).
    var exampleToken: Int?
}

/// A word added from the reader to "My words".
struct ManualWord: Codable, Hashable {
    var key: String
    var tokenID: Int
    var workURN: String
    var added = Date()
}

/// Cards a deck has shown on one day.
struct DayCount: Codable, Hashable {
    var new = 0
    var reviewed = 0     // all cards answered (new ones included), first answer each
}
