import Foundation
import StudyCore

/// The dictionaries the app knows about.
enum Lexicon: String, CaseIterable, Identifiable {
    case lsj, ml, aut, abs, ls, lewis, ccl, crum, klaeber, bt, bdb, strong, md, mw
    case zoega, cleasby = "cv"      // Old Norse: downloaded (lexicon-non.db), not bundled
    var id: String { rawValue }
    var shortName: String {
        switch self {
        case .lsj: return "LSJ"
        case .ml: return "Middle Liddell"
        case .aut: return "Autenrieth"
        case .abs: return "Abbott-Smith"
        case .ls: return "Lewis & Short"
        case .lewis: return "Elementary Lewis"
        case .ccl: return "Coptic Lexicon"
        case .crum: return "Crum"
        case .klaeber: return "Klaeber"
        case .bt: return "Bosworth–Toller"
        case .bdb: return "BDB"
        case .strong: return "Strong's"
        case .md: return "Macdonell"
        case .mw: return "Monier-Williams"
        case .zoega: return "Zoëga"
        case .cleasby: return "Cleasby–Vigfússon"
        }
    }

    /// For a dictionary that comes as a download rather than in lexicon.db:
    /// the language code of its file (Library/lexicon-<code>.db).
    var downloadLanguage: String? {
        switch self {
        case .zoega, .cleasby: return "non"
        default: return nil
        }
    }

    /// Bundled, or downloaded and still on disk.
    var isInstalled: Bool {
        guard let code = downloadLanguage else { return true }
        return FileManager.default.fileExists(atPath: LexiconFiles.url(language: code).path)
    }

    /// The dictionaries offered for a work's language, default first: only
    /// those installed (Old Norse's may not have been downloaded yet).
    static func available(for work: Work) -> [Lexicon] {
        offered(for: work).filter(\.isInstalled)
    }

    /// Every dictionary for a work's language, installed or not.
    static func offered(for work: Work) -> [Lexicon] {
        if work.isOldNorse { return [.zoega, .cleasby] }
        if work.isCoptic { return [.ccl, .crum] }
        if work.isLatin { return [.ls, .lewis] }
        if work.isOldEnglish { return [.klaeber, .bt] }
        if work.isHebrew { return [.bdb, .strong] }
        if work.isSanskrit { return [.md, .mw] }
        if work.isBible { return [.abs, .ml, .lsj] }
        return work.isHomeric ? [.aut, .lsj, .ml] : [.lsj, .ml, .aut]
    }
}

struct LexiconEntry: Identifiable {
    let id: Int
    let lexicon: Lexicon
    let headword: String
    let html: String
    /// How the text's lemma was matched: "exact", "alias", "form" or "accentless".
    let match: String
    var partOfSpeech: String? = nil
}

struct Lookup {
    var shortDefinition: String?
    var entries: [Lexicon: [LexiconEntry]] = [:]
}

/// Downloaded dictionary files, kept beside library.db (Application
/// Support/Library/lexicon-<language>.db) with the same tables as lexicon.db.
enum LexiconFiles {
    static func url(language: String) -> URL {
        LibraryDatabase.directory.appendingPathComponent("lexicon-\(language).db")
    }

    /// Languages whose dictionary file is on disk.
    static func installedLanguages() -> [String] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: LibraryDatabase.directory.path)) ?? []
        return names.compactMap { name in
            guard name.hasPrefix("lexicon-"), name.hasSuffix(".db") else { return nil }
            let code = name.dropFirst("lexicon-".count).dropLast(".db".count)
            return code.isEmpty ? nil : String(code)
        }.sorted()
    }

    /// meta.build of a dictionary file (nil if it has none or won't open).
    static func build(of url: URL) -> String? {
        guard let db = try? SQLiteDatabase(url: url) else { return nil }
        return try? db.string("SELECT value FROM meta WHERE key = 'build'")
    }
}

/// Reads lexicon.db (or a downloaded lexicon-<language>.db) through StudyCore's LexiconReader.
/// Lemma → entry resolution is precomputed by the pipeline (table `resolve`), so a tap is a
/// couple of indexed queries.
final class LexiconStore {
    private let reader: LexiconReader

    init(url: URL) throws {
        reader = try LexiconReader(url: url)
    }

    /// `partOfSpeech` (a Coptic SCRIPTORIUM tag such as "N" or "V") picks
    /// between homographs: ϣⲁϫⲉ the noun "word" vs ϣⲁϫⲉ the verb "speak".
    func lookup(lemmaKey: String, partOfSpeech: String? = nil) -> Lookup {
        var result = Lookup()
        let wanted = Self.posClass(partOfSpeech)
        let resolved = reader.resolve(lemmaKey: lemmaKey)
        for e in resolved.entries {
            guard let lexicon = Lexicon(rawValue: e.dictionary) else { continue }
            result.entries[lexicon, default: []].append(
                LexiconEntry(id: e.id, lexicon: lexicon, headword: e.headword, html: e.html,
                             match: e.match, partOfSpeech: e.partOfSpeech))
        }
        let glosses = resolved.shortDefinitions
        result.shortDefinition = (glosses.first(where: { wanted != nil && $0.partOfSpeech == wanted }) ?? glosses.first)?.text
        if let wanted {
            // the homograph with the right part of speech first
            for (lexicon, entries) in result.entries {
                result.entries[lexicon] = entries.filter { $0.partOfSpeech == wanted }
                    + entries.filter { $0.partOfSpeech != wanted }
            }
        }
        return result
    }

    /// Coptic SCRIPTORIUM tag -> the part-of-speech word the lexicon uses.
    private static func posClass(_ tag: String?) -> String? {
        switch tag?.split(separator: "_").first.map(String.init) {
        case "N", "NPROP": return "noun"
        case "V", "VBD", "VSTAT", "VIMP": return "verb"
        case "ADV": return "adverb"
        case "PREP": return "preposition"
        case "CONJ": return "conjunction"
        case "PTC": return "particle"
        case "NUM": return "numeral"
        default: return nil
        }
    }
}
