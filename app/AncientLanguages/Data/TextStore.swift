import Foundation
import StudyCore

/// Reads works, alignment blocks, Greek segments and tokens from texts.db.
final class TextStore {
    let db: SQLiteDatabase

    init(url: URL, mode: SQLiteDatabase.Mode = .readOnly) throws {
        db = try SQLiteDatabase(url: url, mode: mode)
    }

    func works() throws -> [Work] {
        var out: [Work] = []
        try db.query("""
            SELECT id, urn, author, title, kind, form, greek_urn, english_urn, translator, scope, parse_source,
                   COALESCE(language, 'grc'), COALESCE(credit, '')
            FROM work ORDER BY sort
            """) { r in
            out.append(Work(id: r.int(0), urn: r.string(1) ?? "", author: r.string(2) ?? "",
                            title: r.string(3) ?? "", kind: Work.Kind(rawValue: r.string(4) ?? "") ?? .prose,
                            form: r.string(5) ?? "", greekURN: r.string(6) ?? "",
                            englishURN: r.string(7) ?? "", translator: r.string(8) ?? "",
                            scope: r.string(9) ?? "", parseSource: r.string(10) ?? "",
                            language: r.string(11) ?? "grc", credit: r.string(12) ?? ""))
        }
        return out
    }

    /// Loads a whole work. Even Herodotus (about 185,000 words) loads quickly,
    /// and the reader needs everything to paginate.
    ///
    /// texts.db is the compact form written by pipeline/compact_texts.py: a
    /// token's written form is the slice of its segment's text, lemmas and
    /// tags are shared rows, and a work's tokens are one id range.
    func blocks(for work: Work) throws -> [Block] {
        // segment texts first: tokens take their forms from them
        struct Row { let id, block: Int; let segment: Segment }
        var rows: [Row] = []
        var texts: [Int: NSString] = [:]
        try db.query("""
            SELECT id, block_id, cite, line_n, speaker, heading, part, para_start, text, markers
            FROM segment WHERE work_id = ? ORDER BY seq
            """, [work.id]) { r in
            let id = r.int(0)
            let text = r.string(8) ?? ""
            texts[id] = text as NSString
            rows.append(Row(id: id, block: r.int(1), segment:
                Segment(id: id, cite: r.string(2) ?? "", lineNumber: r.optionalInt(3),
                        speaker: r.string(4), heading: r.string(5), part: r.string(6),
                        paragraphStart: r.int(7) != 0, text: text,
                        markers: Self.decodeMarkers(r.string(9)), tokens: [])))
        }

        var tokens: [Int: [Token]] = [:]
        var range: (Int, Int)?
        try db.query("SELECT token_first, token_last FROM work WHERE id = ?", [work.id]) { r in
            if let first = r.optionalInt(0), let last = r.optionalInt(1) { range = (first, last) }
        }
        if let range {
            let (first, last) = range
            try db.query("""
                SELECT t.id, t.segment_id, t.idx, t.start, t.len, t.form, l.lemma, l.key, g.tag, t.source,
                       t.word_id, a.key
                FROM token t LEFT JOIN lemma l ON l.id = t.lemma_id LEFT JOIN tag g ON g.id = t.tag_id
                LEFT JOIN lemma a ON a.id = t.aor_id
                WHERE t.id BETWEEN ? AND ? ORDER BY t.id
                """, [first, last]) { r in
                let segment = r.int(1)
                let start = r.int(3), length = r.int(4)
                let form = r.string(5) ?? (texts[segment].map {
                    $0.substring(with: NSRange(location: start, length: length)) } ?? "")
                tokens[segment, default: []].append(
                    Token(id: r.int(0), segmentID: segment, index: r.int(2), start: start, end: start + length,
                          form: form, lemma: r.string(6), lemmaKey: r.string(7), postag: r.string(8),
                          source: Self.sources[r.int(9)], wordID: r.optionalInt(10), aoristKey: r.string(11)))
            }
        }

        var segments: [Int: [Segment]] = [:]
        for row in rows {
            let s = row.segment
            segments[row.block, default: []].append(
                Segment(id: s.id, cite: s.cite, lineNumber: s.lineNumber, speaker: s.speaker,
                        heading: s.heading, part: s.part, paragraphStart: s.paragraphStart, text: s.text,
                        markers: s.markers, tokens: tokens[s.id] ?? []))
        }

        var blocks: [Block] = []
        try db.query("""
            SELECT id, cite_start, cite_end, english FROM block WHERE work_id = ? ORDER BY seq
            """, [work.id]) { r in
            let id = r.int(0)
            blocks.append(Block(id: id, citeStart: r.string(1) ?? "", citeEnd: r.string(2) ?? "",
                                english: r.string(3) ?? "", segments: segments[id] ?? []))
        }
        return blocks
    }

    // MARK: Parallel texts (Vulgate ↔ LXX / Greek NT)

    /// For each block of `work` that has a counterpart, the counterpart blocks
    /// (in the other language), in order. Empty if the work has none. The map
    /// is stored by URN and citation, so counterparts in works that aren't
    /// installed are simply left out.
    func parallels(for work: Work) -> [Int: [Int]] {
        var out: [Int: [Int]] = [:]
        try? db.query("""
            SELECT b.id, o.id FROM parallel p
            JOIN block b ON b.work_id = ? AND b.cite_start = p.cite
            JOIN work ow ON ow.urn = p.other_urn
            JOIN block o ON o.work_id = ow.id AND o.cite_start = p.other_cite
            WHERE p.urn = ? ORDER BY b.seq, ow.sort, o.seq
            """, [work.id, work.urn]) { r in
            out[r.int(0), default: []].append(r.int(1))
        }
        return out
    }

    /// The works the given blocks belong to.
    func workIDs(ofBlocks ids: [Int]) -> [Int] {
        guard !ids.isEmpty else { return [] }
        var out: [Int] = []
        let list = Set(ids).map(String.init).joined(separator: ",")
        try? db.query("SELECT DISTINCT work_id FROM block WHERE id IN (\(list))") { r in out.append(r.int(0)) }
        return out
    }

    /// token.source codes (pipeline/compact_texts.py SOURCES)
    private static let sources: [Int: String] = [1: "morpheus", 2: "treebank", 3: "scriptorium", 4: "coptic-nlp",
                                                 5: "oe-forms", 6: "oshb", 7: "dcs", 8: "non-forms"]

    /// Possible analyses of a word form (for works parsed by Morpheus).
    func analyses(of form: String) -> [Analysis] {
        var out: [Analysis] = []
        try? db.query("""
            SELECT a.rank, l.lemma, l.key, p.parse FROM analysis a
            LEFT JOIN lemma l ON l.id = a.lemma_id LEFT JOIN parse p ON p.id = a.parse_id
            WHERE a.form = ? ORDER BY a.rank
            """, [form]) { r in
            out.append(Analysis(rank: r.int(0), lemma: r.string(1) ?? "", lemmaKey: r.string(2) ?? "",
                                parse: r.string(3) ?? ""))
        }
        return out
    }

    /// The morphemes of a Coptic bound group (e.g. ⲛ̄ϣⲁϫⲉ = article + noun), in order.
    func morphs(ofToken id: Int) -> [Analysis] {
        var out: [Analysis] = []
        try? db.query("""
            SELECT m.rank, m.form, l.lemma, l.key, g.tag FROM morph m
            LEFT JOIN lemma l ON l.id = m.lemma_id LEFT JOIN tag g ON g.id = m.tag_id
            WHERE m.token_id = ? ORDER BY m.rank
            """, [id]) { r in
            let pos = ParseFormatter.coptic(r.string(4))
            let form = r.string(1) ?? ""
            out.append(Analysis(rank: r.int(0), lemma: r.string(2) ?? "", lemmaKey: r.string(3) ?? "",
                                parse: form.isEmpty ? pos : "\(form) · \(pos)", tag: r.string(4)))
        }
        return out
    }

    /// Markers are stored as JSON: [[offset, unit, label], …]
    private static func decodeMarkers(_ json: String?) -> [Marker] {
        guard let data = json?.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [[Any]] else { return [] }
        return array.compactMap { item in
            guard item.count == 3, let offset = item[0] as? Int, let unit = item[1] as? String else { return nil }
            return Marker(offset: offset, unit: unit, label: (item[2] as? String) ?? "")
        }
    }
}
