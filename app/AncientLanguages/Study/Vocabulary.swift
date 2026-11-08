import Foundation

/// Reads the words a deck can teach from texts.db (see pipeline/compact_texts.py:
/// the `lemma` table carries glosses, function-word flags and second-aorist
/// entries; `part` gives each book's token range).
final class Vocabulary {
    private let texts: TextStore
    private let works: [Work]

    struct LemmaInfo {
        let id: Int
        let lemma: String
        let key: String
        let gloss: String?
        let isFunction: Bool
        let kind: Int          // 0 word, 1 aorist
        let baseID: Int?
    }

    private var lemmas: [Int: LemmaInfo] = [:]
    private var lemmaByKey: [String: Int] = [:]

    init(texts: TextStore, works: [Work]) {
        self.texts = texts
        self.works = works
    }

    private func loadLemmas() {
        guard lemmas.isEmpty else { return }
        try? texts.db.query("SELECT id, lemma, key, gloss, function, kind, base_id FROM lemma") { r in
            let info = LemmaInfo(id: r.int(0), lemma: r.string(1) ?? "", key: r.string(2) ?? "",
                                 gloss: r.string(3), isFunction: r.int(4) != 0, kind: r.int(5),
                                 baseID: r.optionalInt(6))
            lemmas[info.id] = info
            if lemmaByKey[info.key] == nil || info.gloss != nil { lemmaByKey[info.key] = info.id }
        }
    }

    // MARK: Sources

    struct Part: Hashable { let key: String; let first: Int; let last: Int }

    func parts(of work: Work) -> [Part] {
        var out: [Part] = []
        try? texts.db.query("SELECT key, token_first, token_last FROM part WHERE work_id = ? ORDER BY seq",
                            [work.id]) { r in
            out.append(Part(key: r.string(0) ?? "", first: r.int(1), last: r.int(2)))
        }
        return out
    }

    /// The token id ranges a deck reads, in deck order.
    func ranges(for deck: Deck) -> [(work: Work, first: Int, last: Int)] {
        var out: [(work: Work, first: Int, last: Int)] = []
        for source in deck.sources {
            let chosen = source.author.map { a in works.filter { $0.author == a } }
                ?? works.filter { $0.urn == source.workURN }
            for work in chosen {
                let parts = self.parts(of: work)
                guard !parts.isEmpty else { continue }
                var from = 0, to = parts.count - 1
                if let f = source.fromPart, let i = parts.firstIndex(where: { $0.key == f }) { from = i }
                if let t = source.toPart, let i = parts.firstIndex(where: { $0.key == t }) { to = i }
                guard from <= to else { continue }
                out.append((work: work, first: parts[from].first, last: parts[to].last))
            }
        }
        return out
    }

    // MARK: Entries

    /// Every word the deck can teach, with its count and first appearance.
    func entries(for deck: Deck, myWords: [ManualWord] = [], highlights: [Annotation] = []) -> [VocabEntry] {
        loadLemmas()
        var found: [String: VocabEntry] = [:]
        var position = 0

        func add(_ entry: VocabEntry) {
            if var existing = found[entry.key] {
                existing.count += entry.count
                found[entry.key] = existing
            } else {
                var e = entry
                e.position = position
                position += 1
                found[entry.key] = e
            }
        }

        if deck.isMyWords {
            for word in myWords {
                if let e = entry(forKey: word.key, count: 1, firstToken: word.tokenID) { add(e) }
            }
            if deck.includeHighlights {
                for a in highlights {
                    for (token, lemmaID, aorID) in tokens(of: a) {
                        let id = (deck.separateAorists ? aorID : nil) ?? lemmaID
                        if let e = entry(lemmaID: id, count: 1, firstToken: token) { add(e) }
                    }
                }
            }
            return Array(found.values)
        }

        for (work, first, last) in ranges(for: deck) {
            if deck.allForms {
                for e in formEntries(work: work, first: first, last: last) { add(e) }
                continue
            }
            let column = deck.separateAorists ? "COALESCE(t.aor_id, t.lemma_id)" : "t.lemma_id"
            var rows: [(id: Int, count: Int, first: Int)] = []
            try? texts.db.query("""
                SELECT \(column) AS e, COUNT(*), MIN(t.id) FROM token t
                WHERE t.id BETWEEN ? AND ? AND t.lemma_id IS NOT NULL GROUP BY e ORDER BY MIN(t.id)
                """, [first, last]) { r in rows.append((r.int(0), r.int(1), r.int(2))) }
            for row in rows {
                if let e = entry(lemmaID: row.id, count: row.count, firstToken: row.first) { add(e) }
            }
        }
        return Array(found.values)
    }

    private func entry(lemmaID: Int, count: Int, firstToken: Int) -> VocabEntry? {
        guard let info = lemmas[lemmaID] else { return nil }
        let base = info.baseID.flatMap { lemmas[$0] }
        return VocabEntry(key: info.key, headword: info.lemma.trimmingCharacters(in: .decimalDigits),
                          gloss: info.gloss, kind: info.kind == 1 ? .aorist : .word,
                          baseHeadword: base?.lemma.trimmingCharacters(in: .decimalDigits),
                          lookupKey: base?.key ?? info.key, isFunctionWord: info.isFunction,
                          coptic: Self.isCoptic(info.key), count: count, firstToken: firstToken, position: 0)
    }

    func entry(forKey key: String, count: Int = 1, firstToken: Int = 0) -> VocabEntry? {
        loadLemmas()
        if key.hasPrefix("form:") { return nil }
        return lemmaByKey[key].flatMap { entry(lemmaID: $0, count: count, firstToken: firstToken) }
    }

    /// "All inflected forms": a card per written form, glossed by its lemma.
    private func formEntries(work: Work, first: Int, last: Int) -> [VocabEntry] {
        var texts: [Int: NSString] = [:]
        try? self.texts.db.query("SELECT id, text FROM segment WHERE work_id = ?", [work.id]) { r in
            texts[r.int(0)] = (r.string(1) ?? "") as NSString
        }
        var out: [String: VocabEntry] = [:]
        var order: [String] = []
        try? self.texts.db.query("""
            SELECT t.id, t.segment_id, t.start, t.len, t.form, t.lemma_id FROM token t
            WHERE t.id BETWEEN ? AND ? AND t.lemma_id IS NOT NULL ORDER BY t.id
            """, [first, last]) { r in
            let shown = r.string(4) ?? texts[r.int(1)]?.substring(with: NSRange(location: r.int(2), length: r.int(3))) ?? ""
            let form = Self.normalizedForm(shown)
            guard !form.isEmpty, let info = lemmas[r.int(5)] else { return }
            let key = "form:" + form
            if out[key] != nil {
                out[key]!.count += 1
                return
            }
            order.append(key)
            out[key] = VocabEntry(key: key, headword: form, gloss: info.gloss, kind: .form,
                                  baseHeadword: info.lemma.trimmingCharacters(in: .decimalDigits),
                                  lookupKey: info.key, isFunctionWord: info.isFunction,
                                  coptic: Self.isCoptic(info.key), count: 1, firstToken: r.int(0), position: 0)
        }
        return order.compactMap { out[$0] }
    }

    static func normalizedForm(_ s: String) -> String {
        let trimmed = s.trimmingCharacters(in: CharacterSet(charactersIn: "\u{02BC}\u{2019}'\u{1FBD}"))
        guard let first = trimmed.first else { return "" }
        return (String(first).lowercased() + trimmed.dropFirst()).precomposedStringWithCanonicalMapping
    }

    static func isCoptic(_ s: String) -> Bool {
        s.unicodeScalars.contains { (0x2C80...0x2CFF).contains($0.value) || (0x03E2...0x03EF).contains($0.value) }
    }

    // MARK: Highlights

    /// The words inside a highlight: (token id, lemma id, aorist entry id).
    private func tokens(of a: Annotation) -> [(Int, Int, Int?)] {
        guard let work = works.first(where: { $0.urn == a.workURN }),
              let start = segment(work: work, cite: a.start.cite, occurrence: a.start.occurrence),
              let end = segment(work: work, cite: a.end.cite, occurrence: a.end.occurrence) else { return [] }
        var out: [(Int, Int, Int?)] = []
        try? texts.db.query("""
            SELECT t.id, t.lemma_id, t.aor_id, s.seq, t.start, t.start + t.len FROM token t
            JOIN segment s ON s.id = t.segment_id
            WHERE s.work_id = ? AND s.seq BETWEEN ? AND ? AND t.lemma_id IS NOT NULL ORDER BY t.id
            """, [work.id, start.seq, end.seq]) { r in
            let seq = r.int(3)
            if seq == start.seq && r.int(4) < a.start.offset { return }
            if seq == end.seq && r.int(5) > a.end.offset { return }
            out.append((r.int(0), r.int(1), r.optionalInt(2)))
        }
        return out
    }

    private func segment(work: Work, cite: String, occurrence: Int) -> (id: Int, seq: Int)? {
        var found: (Int, Int)?
        try? texts.db.query("SELECT id, seq FROM segment WHERE work_id = ? AND cite = ? ORDER BY seq LIMIT 1 OFFSET ?",
                            [work.id, cite, occurrence]) { r in found = (r.int(0), r.int(1)) }
        return found
    }

    // MARK: Example line

    struct Example {
        let text: String          // the passage, trimmed around the word
        let wordRange: NSRange    // the word within `text`
        let citation: String
    }

    /// The line (or a stretch of the paragraph) where a token occurs.
    func example(token id: Int) -> Example? {
        var found: Example?
        try? texts.db.query("""
            SELECT s.text, s.cite, s.work_id, t.start, t.len FROM token t JOIN segment s ON s.id = t.segment_id
            WHERE t.id = ?
            """, [id]) { r in
            let text = (r.string(0) ?? "") as NSString
            let start = r.int(3), length = r.int(4)
            let work = works.first { $0.id == r.int(2) }
            let citation = work.map { PerseusLinks.citation(work: $0, cite: r.string(1) ?? "") } ?? (r.string(1) ?? "")
            // keep about 70 characters either side of the word, cut at spaces
            var from = max(0, start - 70), to = min(text.length, start + length + 70)
            if from > 0 {
                let space = text.range(of: " ", options: [], range: NSRange(location: from, length: start - from))
                if space.location != NSNotFound { from = space.location + 1 }
            }
            if to < text.length {
                let space = text.range(of: " ", options: .backwards,
                                       range: NSRange(location: start + length, length: to - start - length))
                if space.location != NSNotFound { to = space.location }
            }
            let piece = text.substring(with: NSRange(location: from, length: to - from))
            let prefix = from > 0 ? "… " : ""
            let suffix = to < text.length ? " …" : ""
            found = Example(text: prefix + piece + suffix,
                            wordRange: NSRange(location: (prefix as NSString).length + start - from, length: length),
                            citation: citation)
        }
        return found
    }
}
