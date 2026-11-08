import Foundation

/// The dictionaries the app knows about.
enum Lexicon: String, CaseIterable, Identifiable {
    case lsj, ml, aut, abs, ls, lewis, ccl, crum, klaeber, bt, bdb, strong, md, mw
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
        }
    }

    /// The dictionaries offered for a work's language, default first.
    static func available(for work: Work) -> [Lexicon] {
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

/// Reads lexicon.db. Lemma → entry resolution is precomputed by the pipeline
/// (table `resolve`), so a tap is a couple of indexed queries.
final class LexiconStore {
    private let db: SQLiteDatabase

    init(url: URL) throws {
        db = try SQLiteDatabase(url: url)
    }

    /// `partOfSpeech` (a Coptic SCRIPTORIUM tag such as "N" or "V") picks
    /// between homographs: ϣⲁϫⲉ the noun "word" vs ϣⲁϫⲉ the verb "speak".
    func lookup(lemmaKey: String, partOfSpeech: String? = nil) -> Lookup {
        var result = Lookup()
        let wanted = Self.posClass(partOfSpeech)
        var targets: [(dict: String, target: Int, how: String)] = []
        try? db.query("SELECT dict, target, how FROM resolve WHERE lemma_key = ? ORDER BY rowid",
                      [lemmaKey]) { r in
            targets.append((r.string(0) ?? "", r.int(1), r.string(2) ?? ""))
        }
        var glosses: [(def: String, pos: String?)] = []
        for t in targets {
            if t.dict == "short" {
                try? db.query("SELECT def, pos FROM shortdef WHERE rowid = ?", [t.target]) { r in
                    if let def = r.string(0) { glosses.append((def, r.string(1))) }
                }
            } else if let lexicon = Lexicon(rawValue: t.dict) {
                try? db.query("SELECT id, headword, html, pos FROM entry WHERE id = ?", [t.target]) { r in
                    let html = Self.inflate(r.data(2)) ?? ""
                    result.entries[lexicon, default: []].append(
                        LexiconEntry(id: r.int(0), lexicon: lexicon, headword: r.string(1) ?? "",
                                     html: html, match: t.how, partOfSpeech: r.string(3)))
                }
            }
        }
        result.shortDefinition = (glosses.first(where: { wanted != nil && $0.pos == wanted }) ?? glosses.first)?.def
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

    /// Entries are stored as raw DEFLATE, which is what Apple calls `.zlib`.
    private static func inflate(_ data: Data?) -> String? {
        guard let data, let out = try? (data as NSData).decompressed(using: .zlib) else { return nil }
        return String(data: out as Data, encoding: .utf8)
    }
}
