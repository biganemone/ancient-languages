import Foundation

/// A reference grammar in grammar.db (pipeline/build_grammar.py): Smyth, Monro.
struct GrammarBook: Identifiable, Hashable {
    let id: String          // "smyth"
    let title: String
    let short: String       // "Smyth"
    let credit: String
}

/// A place in a grammar: "smyth", "1289"; or an entry on an unnumbered page
/// ("smyth", "verbs-β", anchor "v3": βαίνω in Smyth's List of Verbs).
struct GrammarLocation: Hashable {
    let grammar: String
    let n: String
    var anchor: String? = nil
}

/// A numbered section, without its text (for contents and search results).
struct GrammarSection: Identifiable, Hashable {
    let grammar: String
    let n: String
    let heading: String
    let path: String        // "Part IV: Syntax › The Genitive"
    let label: String       // "§1289"; "Verbs: β" for a page of the List of Verbs
    var id: String { "\(grammar)/\(n)" }
    var location: GrammarLocation { GrammarLocation(grammar: grammar, n: n) }
}

/// A section a word's parse points to: "The aorist — Smyth §1923".
struct GrammarRef: Identifiable, Hashable {
    let key: String
    let grammar: String
    let short: String
    let n: String
    let label: String
    var id: String { "\(grammar)/\(n)/\(key)" }
    var location: GrammarLocation { GrammarLocation(grammar: grammar, n: n) }
}

/// A verb's entry in a grammar's list of principal parts (Smyth's List of Verbs).
struct GrammarVerb: Identifiable, Hashable {
    let headword: String    // "βαίνω"
    let short: String       // "Smyth"
    let location: GrammarLocation
    var id: String { "\(location.grammar)/\(location.n)/\(location.anchor ?? "")" }
}

/// The bundled grammar.db, when the app was built with it.
final class GrammarStore {
    private let db: SQLiteDatabase
    let books: [GrammarBook]

    init(url: URL) throws {
        db = try SQLiteDatabase(url: url)
        var books: [GrammarBook] = []
        try db.query("SELECT id, title, short, credit FROM grammar ORDER BY rowid") { r in
            books.append(GrammarBook(id: r.string(0) ?? "", title: r.string(1) ?? "",
                                     short: r.string(2) ?? "", credit: r.string(3) ?? ""))
        }
        self.books = books
    }

    func book(_ id: String) -> GrammarBook? { books.first { $0.id == id } }

    /// The sections for these keys, in the keys' order; Homer's own grammar
    /// (Monro) first for Homeric texts, and only for them.
    func refs(keys: [String], homeric: Bool) -> [GrammarRef] {
        guard !keys.isEmpty else { return [] }
        var found: [GrammarRef] = []
        let marks = keys.map { _ in "?" }.joined(separator: ",")
        try? db.query("SELECT key, grammar, n, label FROM ref WHERE key IN (\(marks))", keys.map { $0 as Any? }) { r in
            let g = r.string(1) ?? ""
            found.append(GrammarRef(key: r.string(0) ?? "", grammar: g, short: book(g)?.short ?? g,
                                    n: r.string(2) ?? "", label: r.string(3) ?? ""))
        }
        if !homeric { found.removeAll { $0.grammar == "monro" } }
        var seen = Set<String>()
        return found
            .sorted { a, b in
                let (ia, ib) = (keys.firstIndex(of: a.key) ?? 0, keys.firstIndex(of: b.key) ?? 0)
                if ia != ib { return ia < ib }
                return (a.grammar == "monro" ? 0 : 1) < (b.grammar == "monro" ? 0 : 1)
            }
            .filter { seen.insert("\($0.grammar)/\($0.n)").inserted }   // one row per section
    }

    /// The entries for this lemma ("λέγω" has two: say, and gather).
    func verbs(lemmaKey: String) -> [GrammarVerb] {
        let key = Self.greekKey(lemmaKey)
        guard !key.isEmpty else { return [] }
        var out: [GrammarVerb] = []
        try? db.query("SELECT headword, grammar, n, anchor FROM verb WHERE key = ? ORDER BY rowid", [key]) { r in
            let g = r.string(1) ?? ""
            out.append(GrammarVerb(headword: r.string(0) ?? "", short: book(g)?.short ?? g,
                                   location: GrammarLocation(grammar: g, n: r.string(2) ?? "", anchor: r.string(3))))
        }
        return out
    }

    /// As pipeline/build_grammar.py's greek_key: letters only (no accents,
    /// breathings, quantity or homograph digits), lower case, σ for ς.
    static func greekKey(_ word: String) -> String {
        String(String.UnicodeScalarView(word.decomposedStringWithCanonicalMapping.unicodeScalars
            .filter { CharacterSet.letters.contains($0) && !CharacterSet.nonBaseCharacters.contains($0) }))
            .lowercased().replacingOccurrences(of: "ς", with: "σ")
    }

    /// Every section, in book order.
    func contents(_ grammar: String) -> [GrammarSection] {
        sections("SELECT grammar, n, heading, path, label FROM section WHERE grammar = ? ORDER BY seq", [grammar])
    }

    /// A section number ("1289", "§1289a") goes straight there; otherwise words in the text.
    func search(_ grammar: String, _ query: String) -> [GrammarSection] {
        let q = query.trimmingCharacters(in: .whitespaces)
        let number = q.trimmingCharacters(in: CharacterSet(charactersIn: "§ "))
        var out: [GrammarSection] = []
        if number.first?.isNumber == true {
            out = sections("SELECT grammar, n, heading, path, label FROM section WHERE grammar = ? AND (n = ? OR n LIKE ?) ORDER BY seq LIMIT 30",
                           [grammar, number, number + "_"])
        }
        let words = sections("SELECT grammar, n, heading, path, label FROM section WHERE grammar = ? AND (plain LIKE ? OR heading LIKE ?) ORDER BY seq LIMIT 200",
                             [grammar, "%\(q)%", "%\(q)%"])
        // a Greek verb, however accented: its page in the List of Verbs
        let key = Self.greekKey(q)
        var verbs: [GrammarSection] = []
        if key.unicodeScalars.contains(where: { (0x370...0x3FF).contains(Int($0.value)) }) {
            verbs = sections("SELECT DISTINCT s.grammar, s.n, s.heading, s.path, s.label FROM verb v JOIN section s ON s.grammar = v.grammar AND s.n = v.n WHERE v.grammar = ? AND v.key LIKE ? ORDER BY s.seq",
                             [grammar, key + "%"])
        }
        var seen = Set<String>()
        return (out + verbs + words).filter { seen.insert($0.id).inserted }
    }

    func section(_ loc: GrammarLocation) -> (section: GrammarSection, html: String)? {
        var result: (section: GrammarSection, html: String)?
        try? db.query("SELECT grammar, n, heading, path, label, html FROM section WHERE grammar = ? AND n = ?",
                      [loc.grammar, loc.n]) { r in
            result = (section: GrammarSection(grammar: r.string(0) ?? "", n: r.string(1) ?? "",
                                              heading: r.string(2) ?? "", path: r.string(3) ?? "",
                                              label: r.string(4) ?? "§" + (r.string(1) ?? "")),
                      html: r.string(5) ?? "")
        }
        return result
    }

    /// The section before (-1) or after (+1) this one in the book.
    func neighbor(of loc: GrammarLocation, _ step: Int) -> GrammarLocation? {
        let sql = step < 0
            ? "SELECT n FROM section WHERE grammar = ?1 AND seq < (SELECT seq FROM section WHERE grammar = ?1 AND n = ?2) ORDER BY seq DESC LIMIT 1"
            : "SELECT n FROM section WHERE grammar = ?1 AND seq > (SELECT seq FROM section WHERE grammar = ?1 AND n = ?2) ORDER BY seq LIMIT 1"
        var n: String?
        try? db.query(sql, [loc.grammar, loc.n]) { r in n = r.string(0) }
        return n.map { GrammarLocation(grammar: loc.grammar, n: $0) }
    }

    private func sections(_ sql: String, _ args: [Any?]) -> [GrammarSection] {
        var out: [GrammarSection] = []
        try? db.query(sql, args) { r in
            out.append(GrammarSection(grammar: r.string(0) ?? "", n: r.string(1) ?? "",
                                      heading: r.string(2) ?? "", path: r.string(3) ?? "",
                                      label: r.string(4) ?? "§" + (r.string(1) ?? "")))
        }
        return out
    }
}

/// A parse as the lookup card shows it ("verb · aorist · indicative · active ·
/// 3rd person · singular") -> the grammar keys of pipeline/build_grammar.py's RULES.
enum GrammarKeys {
    private static let tenses = ["present", "imperfect", "future", "aorist", "perfect", "pluperfect", "future perfect"]
    private static let moods = ["indicative", "subjunctive", "optative", "imperative", "infinitive", "participle"]
    private static let cases = ["nominative", "genitive", "dative", "accusative", "vocative"]
    private static let kinds = ["article", "pronoun", "adjective", "preposition", "particle", "conjunction", "adverb"]

    static func keys(parse: String, irregularAorist: Bool = false) -> [String] {
        // "nominative/vocative" and "noun/adjective" are each several words
        let words = parse.components(separatedBy: " · ").flatMap { $0.components(separatedBy: "/") }
        let has = Set(words)
        var keys: [String] = []
        let tense = tenses.last { has.contains($0) }      // "future perfect" over "future"
        let isVerb = has.contains("verb") || has.contains("participle") || tense != nil
        if isVerb {
            if let tense { keys.append("tense:\(tense)") }
            if has.contains("participle") { keys.append("mood:participle") }
            for m in moods where m != "participle" && has.contains(m) { keys.append("mood:\(m)") }
            if has.contains("active") { keys.append("voice:active") }
            if has.contains("middle") || has.contains("middle-passive") { keys.append("voice:middle") }
            if has.contains("passive") || has.contains("middle-passive") { keys.append("voice:passive") }
            if irregularAorist { keys.append("aorist2") }
            if has.contains("indicative"), let tense, ["imperfect", "aorist", "pluperfect"].contains(tense) {
                keys.append("augment")
            }
            if let tense, ["perfect", "pluperfect", "future perfect"].contains(tense) { keys.append("reduplication") }
            if has.contains("indicative") || has.contains("subjunctive") || has.contains("optative")
                || has.contains("imperative") { keys.append("endings:verb") }
        }
        // one case only: "nominative/vocative/accusative" would be a list, not a pointer
        let caseWords = cases.filter { has.contains($0) }
        if caseWords.count == 1 { keys.append("case:\(caseWords[0])") }
        if !isVerb {
            for k in kinds where has.contains(k) {
                if k == "adjective" && has.contains("noun") { continue }   // "noun/adjective": don't guess
                keys.append("pos:\(k)")
            }
            if has.contains("article") { keys.append("forms:article") }
            if has.contains("numeral") { keys.append("forms:numeral") }
            if has.contains("comparative") || has.contains("superlative") { keys.append("degree") }
        }
        return keys
    }
}
