import Foundation
import Observation
import SwiftUI
import UIKit

/// A place in a text that survives rebuilding the databases: the segment's
/// citation ("1.120", "5d", "17.4"), which occurrence of that citation it is
/// (a Stephanus section can hold several paragraphs), and a UTF-16 offset into
/// the segment's text. Database row ids are never stored.
struct TextPoint: Codable, Hashable {
    var cite: String
    var occurrence: Int
    var offset: Int
}

enum HighlightColor: String, Codable, CaseIterable, Identifiable {
    case yellow, green, blue, pink

    var id: String { rawValue }

    var name: String { rawValue.capitalized }

    /// Soft enough to read through in light and dark mode.
    var uiColor: UIColor {
        let (r, g, b): (CGFloat, CGFloat, CGFloat) = switch self {
        case .yellow: (0.98, 0.82, 0.25)
        case .green: (0.45, 0.80, 0.45)
        case .blue: (0.40, 0.65, 0.95)
        case .pink: (0.95, 0.50, 0.65)
        }
        return UIColor { traits in
            UIColor(red: r, green: g, blue: b, alpha: traits.userInterfaceStyle == .dark ? 0.38 : 0.42)
        }
    }

    /// Full strength, for swatches.
    var swatch: UIColor { uiColor.withAlphaComponent(1) }
}

/// A highlight, with or without a note, over a run of words.
struct Annotation: Codable, Identifiable, Hashable {
    var id = UUID()
    var workURN: String
    var start: TextPoint      // offset of the first word's start
    var end: TextPoint        // offset of the last word's end
    var quote: String         // the words, as they read when the note was made
    var color: HighlightColor
    var note: String = ""
    var created = Date()
    var modified = Date()

    var hasNote: Bool { !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
}

/// A marked place: the start of the passage at the top of the page (or of
/// the screen, when scrolling).
struct Bookmark: Codable, Identifiable, Hashable {
    var id = UUID()
    var workURN: String
    var point: TextPoint
    var snippet: String       // the first words there, to recognise it in a list
    var created = Date()
}

/// All highlights, notes and bookmarks, kept as JSON files in Application
/// Support. Small enough to load whole; written after every change.
@Observable
final class AnnotationStore {
    static let shared = AnnotationStore()

    private(set) var all: [Annotation] = []
    private(set) var bookmarks: [Bookmark] = []
    private let url: URL?
    private let bookmarksURL: URL?

    init(directory: URL? = AnnotationStore.defaultDirectory) {
        url = directory?.appendingPathComponent("annotations.json")
        bookmarksURL = directory?.appendingPathComponent("bookmarks.json")
        all = Self.read([Annotation].self, from: url) ?? []
        bookmarks = Self.read([Bookmark].self, from: bookmarksURL) ?? []
    }

    static var defaultDirectory: URL? {
        try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                     appropriateFor: nil, create: true)
    }

    private static func read<T: Decodable>(_ type: T.Type, from url: URL?) -> T? {
        guard let url, let data = try? Data(contentsOf: url) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try? decoder.decode(type, from: data)
    }

    private static func write<T: Encodable>(_ value: T, to url: URL?) {
        guard let url else { return }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(value) {
            try? data.write(to: url, options: .atomic)
        }
    }

    // MARK: Bookmarks

    func bookmarks(for workURN: String) -> [Bookmark] {
        bookmarks.filter { $0.workURN == workURN }
    }

    func addBookmark(_ bookmark: Bookmark) {
        bookmarks.append(bookmark)
        Self.write(bookmarks, to: bookmarksURL)
    }

    func deleteBookmark(_ id: UUID) {
        bookmarks.removeAll { $0.id == id }
        Self.write(bookmarks, to: bookmarksURL)
    }

    // MARK: Highlights and notes

    func annotations(for workURN: String) -> [Annotation] {
        all.filter { $0.workURN == workURN }
    }

    func save(_ annotation: Annotation) {
        var a = annotation
        a.modified = Date()
        if let i = all.firstIndex(where: { $0.id == a.id }) {
            all[i] = a
        } else {
            all.append(a)
        }
        persist()
    }

    func delete(_ id: UUID) {
        all.removeAll { $0.id == id }
        persist()
    }

    /// Remove the note but keep the highlight.
    func deleteNote(of id: UUID) {
        guard let i = all.firstIndex(where: { $0.id == id }) else { return }
        all[i].note = ""
        all[i].modified = Date()
        persist()
    }

    private func persist() {
        Self.write(all, to: url)
    }
}

/// How one word should look: painted by a highlight (or the selection being
/// made), and whether that highlight has a note (shown as a dotted underline).
struct TokenMark {
    let owner: UUID          // the annotation, so neighbouring words join up
    let color: UIColor
    let hasNote: Bool
}

/// The segments of a whole work in reading order, with the stable keys that
/// annotations use.
struct SegmentIndex {
    private(set) var ordered: [Segment] = []
    private(set) var order: [Int: Int] = [:]        // segment id -> position in `ordered`
    private(set) var part: [Int: Int] = [:]         // segment id -> part index
    private var occurrence: [Int: Int] = [:]        // segment id -> nth segment with that cite
    private var byKey: [String: Int] = [:]          // "cite#n" -> segment id
    private(set) var firstOfBlock: [Int: Int] = [:] // block id -> its first segment id

    static let selectionOwner = UUID()

    init() {}

    init(parts: [WorkPart]) {
        var seen: [String: Int] = [:]
        for part in parts {
            for block in part.blocks {
                if let first = block.segments.first { firstOfBlock[block.id] = first.id }
                for segment in block.segments {
                    let n = seen[segment.cite, default: 0]
                    seen[segment.cite] = n + 1
                    order[segment.id] = ordered.count
                    ordered.append(segment)
                    self.part[segment.id] = part.id
                    occurrence[segment.id] = n
                    byKey["\(segment.cite)#\(n)"] = segment.id
                }
            }
        }
    }

    func point(segmentID: Int, offset: Int) -> TextPoint? {
        guard let i = order[segmentID], let n = occurrence[segmentID] else { return nil }
        return TextPoint(cite: ordered[i].cite, occurrence: n, offset: offset)
    }

    func segmentID(for point: TextPoint) -> Int? {
        byKey["\(point.cite)#\(point.occurrence)"]
    }

    /// Reading order of two words.
    func precedes(_ a: Token, _ b: Token) -> Bool {
        let (oa, ob) = (order[a.segmentID] ?? 0, order[b.segmentID] ?? 0)
        return oa != ob ? oa < ob : a.index <= b.index
    }

    /// The words from `start` to `end`, in order.
    func tokens(from start: TextPoint, to end: TextPoint) -> [Token] {
        guard let s = segmentID(for: start).flatMap({ order[$0] }),
              let e = segmentID(for: end).flatMap({ order[$0] }), s <= e else { return [] }
        var out: [Token] = []
        for i in s...e {
            for t in ordered[i].tokens
            where (i != s || t.start >= start.offset) && (i != e || t.end <= end.offset) {
                out.append(t)
            }
        }
        return out
    }

    func tokens(from a: Token, to b: Token) -> [Token] {
        var (first, last) = precedes(a, b) ? (a, b) : (b, a)
        first = pieces(of: first).first ?? first
        last = pieces(of: last).last ?? last
        guard let s = point(segmentID: first.segmentID, offset: first.start),
              let e = point(segmentID: last.segmentID, offset: last.end) else { return [first] }
        return tokens(from: s, to: e)
    }

    /// The pieces of a word broken across lines (Coptic codices), in order;
    /// just the word itself otherwise.
    func pieces(of token: Token) -> [Token] {
        guard let word = token.wordID, let i = order[token.segmentID] else { return [token] }
        let nearby = ordered[max(0, i - 3)...min(ordered.count - 1, i + 3)]
        return nearby.flatMap(\.tokens).filter { $0.wordID == word }
    }

    /// An annotation for the words from `a` to `b` (either order). A word
    /// broken across lines is taken whole.
    func annotation(from a: Token, to b: Token, workURN: String, color: HighlightColor) -> Annotation? {
        var (first, last) = precedes(a, b) ? (a, b) : (b, a)
        first = pieces(of: first).first ?? first
        last = pieces(of: last).last ?? last
        guard let s = point(segmentID: first.segmentID, offset: first.start),
              let e = point(segmentID: last.segmentID, offset: last.end) else { return nil }
        return Annotation(workURN: workURN, start: s, end: e, quote: quote(from: s, to: e), color: color)
    }

    /// The text from `start` to `end`, segments joined by spaces.
    func quote(from start: TextPoint, to end: TextPoint) -> String {
        guard let s = segmentID(for: start).flatMap({ order[$0] }),
              let e = segmentID(for: end).flatMap({ order[$0] }), s <= e else { return "" }
        var pieces: [String] = []
        for i in s...e {
            let text = ordered[i].text as NSString
            let from = i == s ? min(start.offset, text.length) : 0
            let to = i == e ? min(end.offset, text.length) : text.length
            if to > from { pieces.append(text.substring(with: NSRange(location: from, length: to - from))) }
        }
        return pieces.joined(separator: " ")
    }

    func covers(_ annotation: Annotation, _ token: Token) -> Bool {
        tokens(from: annotation.start, to: annotation.end).contains { $0.isSameWord(as: token) }
    }

    /// Marks for every annotated word (keyed by token row id), with the
    /// selection being made drawn over them.
    func marks(for annotations: [Annotation], selection: (Token, Token)?) -> [Int: TokenMark] {
        var out: [Int: TokenMark] = [:]
        for a in annotations.sorted(by: { $0.created < $1.created }) {
            let mark = TokenMark(owner: a.id, color: a.color.uiColor, hasNote: a.hasNote)
            for t in tokens(from: a.start, to: a.end) { out[t.id] = mark }
        }
        if let pair = selection {
            let (a, b) = pair
            let mark = TokenMark(owner: Self.selectionOwner,
                                 color: UIColor.tintColor.withAlphaComponent(0.28), hasNote: false)
            for t in tokens(from: a, to: b) { out[t.id] = mark }
        }
        return out
    }
}

/// What the reader's text views need to draw highlights and start a new one.
/// Passed down through the environment so the paged and scrolling readers
/// don't each have to thread it through.
struct ReaderAnnotationContext {
    var marks: [Int: TokenMark] = [:]
    var onLongPress: ((Token) -> Void)? = nil
}

private struct ReaderAnnotationKey: EnvironmentKey {
    static let defaultValue = ReaderAnnotationContext()
}

extension EnvironmentValues {
    var readerAnnotations: ReaderAnnotationContext {
        get { self[ReaderAnnotationKey.self] }
        set { self[ReaderAnnotationKey.self] = newValue }
    }
}
