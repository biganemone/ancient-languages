import Foundation

enum TranslationLayout: String, CaseIterable, Identifiable {
    case greekOnly, interleaved, sideBySide
    var id: String { rawValue }
    var label: String {
        switch self {
        case .greekOnly: return "Original only"
        case .interleaved: return "With translation blocks"
        case .sideBySide: return "Side by side"
        }
    }
}

/// Keys for @AppStorage so every view agrees.
enum SettingsKey {
    static let showNumbers = "showNumbers"           // line / Stephanus numbers
    static let fontSize = "greekFontSize"
    static let hebrewFontSize = "hebrewFontSize"     // Hebrew is set larger, and sized on its own
    static let devanagariFontSize = "devanagariFontSize"   // so is Devanāgarī
    static let layout = "translationLayout"
    static let lexicon = "defaultLexicon"
    static let copticLexicon = "defaultCopticLexicon"
    static let homericLexicon = "defaultHomericLexicon"     // Autenrieth unless changed
    static let ntLexicon = "defaultNTLexicon"               // Abbott-Smith unless changed
    static let latinLexicon = "defaultLatinLexicon"         // Lewis & Short unless changed
    static let oldEnglishLexicon = "defaultOldEnglishLexicon" // Klaeber unless changed
    static let oldNorseLexicon = "defaultOldNorseLexicon"   // Zoëga unless changed
    static let hebrewLexicon = "defaultHebrewLexicon"       // BDB unless changed
    static let sanskritLexicon = "defaultSanskritLexicon"   // Macdonell unless changed
    static let hideCantillation = "hideCantillation"        // Hebrew: show vowel points only
    static let devanagari = "sanskritDevanagari"            // Sanskrit in Devanāgarī rather than IAST
    static let parallel = "parallelLanguage"                // "", "Greek", "Latin", "Coptic": the text read alongside
    static let paged = "pagedReading"                // turn pages (default) vs scroll
    static let positions = "readingPositions"        // where each work was left
    static let libraryLanguage = "libraryLanguage"   // the language shown in the Read tab
    static let rootTab = "rootTab"                   // Read or Study, where the app was left
    static let collapsedAuthors = "collapsedAuthors" // library groups closed by the reader
    static let focusButton = "showFocusButton"       // the floating hide-the-bars button
}

/// The Read tab's languages, in the order they're shown.
enum LibraryLanguage: String, CaseIterable, Identifiable {
    case greek, latin, hebrew, sanskrit, coptic, oldEnglish, oldNorse
    var id: String { rawValue }
    var label: String {
        switch self {
        case .greek: return "Greek"
        case .latin: return "Latin"
        case .coptic: return "Coptic"
        case .oldEnglish: return "Old English"
        case .oldNorse: return "Old Norse"
        case .hebrew: return "Hebrew"
        case .sanskrit: return "Sanskrit"
        }
    }
    /// The language code works carry (Work.language, catalog.json).
    var code: String {
        switch self {
        case .greek: return "grc"
        case .latin: return "lat"
        case .coptic: return "cop"
        case .oldEnglish: return "ang"
        case .oldNorse: return "non"
        case .hebrew: return "hbo"
        case .sanskrit: return "san"
        }
    }
    init?(code: String) {
        guard let match = Self.allCases.first(where: { $0.code == (code.isEmpty ? "grc" : code) }) else { return nil }
        self = match
    }
}

/// The app's tabs.
enum RootTab: String {
    case read, study, reference
}
