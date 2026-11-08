import SwiftUI
import CoreText

/// One displayable piece of a work in reading order. Both the scrolling and
/// the paged reader show lists of these; the paginator may cut a prose
/// paragraph or an English block in two.
struct ReaderItem: Identifiable {
    /// `row`: side-by-side layout (iPad). A block's Greek items in the left
    /// column (`columns`) and its English (`rowEnglish`) in the right.
    enum Kind { case greek, english, heading, speaker, row }

    let id: String
    let kind: Kind
    /// Stable across re-pagination: "g<segment id>", "e<block id>", "h…", "s…".
    let baseID: String
    let cite: String
    /// Where this piece starts within the full item's text (non-zero for the
    /// second half of a split paragraph).
    let startLocation: Int
    let content: ReaderText.Content
    let gutterLabel: String
    var topGap: CGFloat
    var bottomGap: CGFloat
    /// Rows only: the Greek column, and the English beside it.
    var columns: [ReaderItem] = []
    var rowEnglish: ReaderText.Content? = nil
    /// Rows with a parallel text: its verses in the right column (tappable),
    /// in place of the English.
    var rowCompanion: [ReaderItem] = []
    /// Set on the parallel text's items (the Greek beside the Vulgate, the
    /// Latin beside the LXX/NT): taps look the word up in that work.
    var companionWork: Work? = nil
    var isTranslationSide: Bool { kind == .english || companionWork != nil }

    /// Headings and speaker names must not end a page.
    var keepWithNext: Bool { kind == .heading || kind == .speaker }

    /// Citations of the Greek on show (for the page footer).
    var greekCites: [String] {
        switch kind {
        case .greek: return companionWork == nil ? [cite] : []
        case .row: return columns.flatMap(\.greekCites)
        default: return []
        }
    }

    /// The next piece of a row cut across pages.
    func renumbered(_ piece: Int) -> ReaderItem {
        var copy = ReaderItem(id: "\(baseID)#\(piece)", kind: kind, baseID: baseID, cite: cite,
                              startLocation: piece, content: content, gutterLabel: gutterLabel,
                              topGap: topGap, bottomGap: bottomGap)
        copy.columns = columns
        copy.rowEnglish = rowEnglish
        copy.rowCompanion = rowCompanion
        copy.companionWork = companionWork
        return copy
    }

    func with(content: ReaderText.Content, startLocation: Int, id: String, gutterLabel: String,
              topGap: CGFloat, bottomGap: CGFloat) -> ReaderItem {
        var copy = ReaderItem(id: id, kind: kind, baseID: baseID, cite: cite, startLocation: startLocation,
                              content: content, gutterLabel: gutterLabel, topGap: topGap, bottomGap: bottomGap)
        copy.companionWork = companionWork
        return copy
    }
}

/// A reading position that survives re-pagination (rotation, text size, …).
struct ReaderAnchor: Equatable {
    let baseID: String
    let location: Int
}

struct ReaderContent {
    var items: [ReaderItem] = []
    /// Where each Greek segment starts, for "go to" and links.
    var segmentAnchors: [Int: ReaderAnchor] = [:]
    var segmentCites: [Int: String] = [:]
    /// Where each block's Greek starts (to keep the place when English blocks disappear).
    var blockAnchors: [Int: ReaderAnchor] = [:]

    /// An anchor that exists in these items, given one that may come from a
    /// different layout (joined paragraphs, English blocks shown or hidden).
    func resolve(_ anchor: ReaderAnchor) -> ReaderAnchor? {
        if items.contains(where: { $0.baseID == anchor.baseID }) { return anchor }
        let id = Int(anchor.baseID.dropFirst())
        switch anchor.baseID.first {
        case "g", "h", "s": return id.flatMap { segmentAnchors[$0] }
        case "e": return id.flatMap { blockAnchors[$0] }
        case "r": return id.flatMap { blockAnchors[$0] }
        default: return nil
        }
    }
}

enum ReaderItems {
    /// `companion`: for a work read with its parallel text (Vulgate ↔ LXX /
    /// Greek NT), each block's counterpart blocks and the works they belong to.
    /// They take the English's place: beside the text, or between its verses.
    static func make(blocks: [Block], work: Work, layout: TranslationLayout, metrics: ReaderMetrics,
                     companion: [Int: [Block]] = [:], companionWork: [Int: Work] = [:]) -> ReaderContent {
        var out = ReaderContent()
        var sharedLineIndent: CGFloat = 0       // for verse lines split between speakers
        var previousVerse: (part: String?, width: CGFloat)?

        for block in blocks {
            let blockStart = out.items.count
            for segment in block.segments {
                out.segmentCites[segment.id] = segment.cite
                defer {
                    if out.blockAnchors[block.id] == nil { out.blockAnchors[block.id] = out.segmentAnchors[segment.id] }
                }
                var startsAfterLabel = false

                if let heading = segment.heading, !heading.isEmpty {
                    let major = heading.hasPrefix("Book") || heading.hasPrefix("Hymn ")
                    out.items.append(ReaderItem(
                        id: "h\(segment.id)", kind: .heading, baseID: "h\(segment.id)", cite: segment.cite,
                        startLocation: 0, content: ReaderText.heading(heading, fontSize: metrics.fontSize, major: major),
                        gutterLabel: "", topGap: metrics.fontSize * (major ? 1.4 : 0.7),
                        bottomGap: metrics.fontSize * (major ? 0.6 : 0.1)))
                    startsAfterLabel = true
                }
                if work.isDrama, let speaker = segment.speaker, !speaker.isEmpty {
                    out.items.append(ReaderItem(
                        id: "s\(segment.id)", kind: .speaker, baseID: "s\(segment.id)", cite: segment.cite,
                        startLocation: 0, content: ReaderText.speaker(speaker, fontSize: metrics.fontSize),
                        gutterLabel: "", topGap: startsAfterLabel ? 0 : metrics.speechGap,
                        bottomGap: metrics.fontSize * 0.08))
                    startsAfterLabel = true
                }

                switch work.kind {
                case .verse:
                    // The second (or third) part of a line shared between speakers
                    // starts where the previous part ended.
                    var indent: CGFloat = 0
                    if let part = segment.part, part == "M" || part == "F",
                       let previous = previousVerse, previous.part == "I" || previous.part == "M" {
                        indent = sharedLineIndent + previous.width + metrics.fontSize * 0.5
                    }
                    let content = ReaderText.greek(segment.text, tokens: segment.tokens, fontSize: metrics.textFontSize,
                                                   hangingIndent: max(metrics.hangingIndent, indent),
                                                   firstLineIndent: indent, coptic: metrics.coptic,
                                                   rtl: metrics.rtl, hideMarks: metrics.hideCantillation,
                                                   devanagari: metrics.devanagari)
                    sharedLineIndent = indent
                    previousVerse = (segment.part, ceil(content.string.size().width))   // size() ignores indents
                    let gap = startsAfterLabel ? 0
                        : (segment.paragraphStart && segment.lineNumber != 1 ? metrics.verseParagraphGap : 0)
                    out.segmentAnchors[segment.id] = ReaderAnchor(baseID: "g\(segment.id)", location: 0)
                    out.items.append(ReaderItem(
                        id: "g\(segment.id)", kind: .greek, baseID: "g\(segment.id)", cite: segment.cite,
                        startLocation: 0, content: content, gutterLabel: lineLabel(segment),
                        topGap: gap, bottomGap: 0))

                case .prose:
                    var insertions: [ReaderText.Insertion] = []
                    if let speaker = segment.speaker, !speaker.isEmpty {
                        insertions.append(.init(offset: 0, text: speaker + " ", style: .speaker))
                    }
                    // Manuscript page breaks inside a paragraph (Coptic codices)
                    if metrics.showNumbers {
                        for m in segment.markers where m.unit == "page" && m.offset > 0 {
                            insertions.append(.init(offset: m.offset, text: "\u{2009}p.\u{202F}\(m.label)\u{2009}",
                                                    style: .marker))
                        }
                    }
                    let content = ReaderText.greek(segment.text, tokens: segment.tokens, insertions: insertions,
                                                   fontSize: metrics.textFontSize, hangingIndent: 0,
                                                   coptic: metrics.coptic, rtl: metrics.rtl,
                                                   hideMarks: metrics.hideCantillation, devanagari: metrics.devanagari)
                    let section = segment.markers.first(where: { $0.offset == 0 && $0.unit == "section" })?.label ?? ""

                    // A paragraph that runs across a section (or verse) break stays
                    // one paragraph, with the number inline (or none, if numbers
                    // are hidden). Greek only: across blocks too; with English,
                    // within its block.
                    if layout == .greekOnly || out.items.count > blockStart, !segment.paragraphStart,
                       !startsAfterLabel, let last = out.items.last, last.kind == .greek {
                        let separator = metrics.showNumbers && !section.isEmpty
                            ? ReaderText.inlineMarker(section, fontSize: metrics.fontSize)
                            : NSAttributedString(string: " ", attributes: [.font: metrics.textFont])
                        let joined = ReaderText.join(last.content, separator, content)
                        let offset = joined.string.length - content.string.length
                        out.items[out.items.count - 1] = last.with(
                            content: joined, startLocation: last.startLocation, id: last.id,
                            gutterLabel: last.gutterLabel, topGap: last.topGap, bottomGap: last.bottomGap)
                        out.segmentAnchors[segment.id] = ReaderAnchor(baseID: last.baseID, location: offset)
                        continue
                    }
                    out.segmentAnchors[segment.id] = ReaderAnchor(baseID: "g\(segment.id)", location: 0)
                    out.items.append(ReaderItem(
                        id: "g\(segment.id)", kind: .greek, baseID: "g\(segment.id)", cite: segment.cite,
                        startLocation: 0, content: content, gutterLabel: section,
                        topGap: startsAfterLabel ? 0 : (segment.paragraphStart ? metrics.speechGap : metrics.fontSize * 0.2),
                        bottomGap: 0))
                }
            }
            if layout != .greekOnly, let others = companion[block.id], !others.isEmpty {
                let items = companionItems(others, for: block, works: companionWork, metrics: metrics, into: &out)
                if layout == .sideBySide, out.items.count > blockStart {
                    makeRow(block: block, from: blockStart, into: &out, metrics: metrics, companion: items)
                } else {
                    out.items.append(contentsOf: items)
                }
            } else if layout == .sideBySide, !block.english.isEmpty, out.items.count > blockStart {
                makeRow(block: block, from: blockStart, into: &out, metrics: metrics)
            } else if layout == .interleaved, !block.english.isEmpty {
                out.items.append(ReaderItem(
                    id: "e\(block.id)", kind: .english, baseID: "e\(block.id)", cite: block.citeStart,
                    startLocation: 0, content: ReaderText.english(block.english, fontSize: metrics.fontSize),
                    gutterLabel: "", topGap: metrics.englishOuterGap, bottomGap: metrics.englishOuterGap))
            }
        }
        if !out.items.isEmpty, out.items[0].kind != .heading {
            out.items[0].topGap = 0
        }
        return out
    }

    /// Side by side: replaces the block's items (from `start`) with one row,
    /// Greek on the left and English on the right. A heading that opens the
    /// block (e.g. "Book 2") stays above the row, across both columns.
    private static func makeRow(block: Block, from start: Int, into out: inout ReaderContent,
                                metrics: ReaderMetrics, companion: [ReaderItem] = []) {
        var greek = Array(out.items[start...])
        out.items.removeSubrange(start...)
        while let first = greek.first, first.kind == .heading {
            out.items.append(first)
            greek.removeFirst()
        }
        guard !greek.isEmpty else { return }
        greek[0].topGap = 0
        let baseID = "r\(block.id)"
        let anchor = ReaderAnchor(baseID: baseID, location: 0)
        for segment in block.segments { out.segmentAnchors[segment.id] = anchor }
        out.blockAnchors[block.id] = anchor
        var row = ReaderItem(id: baseID, kind: .row, baseID: baseID, cite: block.citeStart, startLocation: 0,
                             content: .empty, gutterLabel: "",
                             topGap: out.items.last?.kind == .heading ? 0 : metrics.englishOuterGap * 1.5,
                             bottomGap: 0)
        row.columns = greek
        if companion.isEmpty {
            row.rowEnglish = ReaderText.english(block.english, fontSize: metrics.fontSize)
        } else {
            row.rowCompanion = companion.enumerated().map { i, item in
                var item = item
                if i == 0 { item.topGap = 0 }
                return item
            }
        }
        out.items.append(row)
    }

    /// The parallel text for one block: a tappable item per verse, numbered
    /// in the gutter with its own citation ("Ps 22:1" may be the Greek 22:1
    /// or 23:1). A counterpart verse shared by two blocks appears with each.
    private static func companionItems(_ others: [Block], for block: Block, works: [Int: Work],
                                       metrics: ReaderMetrics, into out: inout ReaderContent) -> [ReaderItem] {
        var items: [ReaderItem] = []
        for other in others {
            let otherWork = works[other.id]
            for s in other.segments {
                out.segmentCites[s.id] = s.cite
                let content = ReaderText.greek(s.text, tokens: s.tokens,
                                               fontSize: metrics.textFontSize(hebrew: otherWork?.isHebrew ?? false),
                                               hangingIndent: 0, coptic: otherWork?.isCoptic ?? false,
                                               rtl: otherWork?.isHebrew ?? false, hideMarks: metrics.hideCantillation)
                let id = "c\(block.id)-\(s.id)"
                let label = otherWork?.isBible == true ? s.cite.replacingOccurrences(of: ".", with: ":") : s.cite
                var item = ReaderItem(id: id, kind: .greek, baseID: id, cite: s.cite, startLocation: 0,
                                      content: content, gutterLabel: label,
                                      topGap: items.isEmpty ? metrics.englishOuterGap : metrics.fontSize * 0.2,
                                      bottomGap: 0)
                item.companionWork = otherWork
                items.append(item)
            }
        }
        if !items.isEmpty { items[items.count - 1].bottomGap = metrics.englishOuterGap }
        return items
    }

    /// Traditional practice: number line 1 and every fifth line (the first
    /// part only, when a line is shared between speakers).
    private static func lineLabel(_ segment: Segment) -> String {
        guard let n = segment.lineNumber, n == 1 || n % 5 == 0 else { return "" }
        if let part = segment.part, part == "M" || part == "F" { return "" }
        return String(n)
    }
}

// MARK: - Views shared by both reading modes

/// Two columns, Greek and English, split as `ReaderMetrics.columnWidths`
/// says (the paginator measures with the same widths).
struct RowColumns: Layout {
    let gap: CGFloat

    private func widths(_ total: CGFloat) -> (CGFloat, CGFloat) {
        let greek = ((total - gap) * ReaderMetrics.greekColumnShare).rounded(.down)
        return (greek, total - gap - greek)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width ?? 700
        let (g, e) = widths(total)
        let heights = zip(subviews, [g, e]).map { $0.sizeThatFits(ProposedViewSize(width: $1, height: nil)).height }
        return CGSize(width: total, height: heights.max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (g, e) = widths(bounds.width)
        var x = bounds.minX
        for (view, width) in zip(subviews, [g, e]) {
            view.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading,
                       proposal: ProposedViewSize(width: width, height: nil))
            x += width + gap
        }
    }
}

struct ReaderItemView: View {
    let item: ReaderItem
    let metrics: ReaderMetrics
    let selection: WordSelection?
    let onTapToken: (Token, ReaderItem, CGFloat) -> Void
    let onTapBackground: () -> Void

    @Environment(\.readerAnnotations) private var annotations

    /// Hebrew (the work, or a Hebrew parallel beside it) runs right to left:
    /// the number gutter, indents and columns mirror.
    private var direction: LayoutDirection {
        let rtl = item.companionWork.map(\.isHebrew) ?? metrics.rtl
        return rtl ? .rightToLeft : .leftToRight
    }

    var body: some View {
        itemBody.environment(\.layoutDirection, direction)
    }

    @ViewBuilder private var itemBody: some View {
        switch item.kind {
        case .greek:
            HStack(alignment: .top, spacing: metrics.gutterSpacing) {
                if metrics.showNumbers {
                    NumberGutter(label: item.gutterLabel, metrics: metrics)
                        .onTapGesture(perform: onTapBackground)
                }
                GreekTextView(content: item.content,
                              highlighted: selection?.token,
                              marks: item.companionWork == nil ? annotations.marks : [:],
                              onLongPressToken: item.companionWork == nil ? annotations.onLongPress : nil,
                              onTapToken: { token, y in onTapToken(token, item, y) },
                              onTapBackground: onTapBackground)
                    // the parallel text: a thin rule down its left side
                    .overlay(alignment: .leading) {
                        if item.companionWork != nil {
                            Rectangle().fill(Color(Palette.muted).opacity(0.45)).frame(width: 2)
                                .offset(x: -metrics.fontSize * 0.35)
                        }
                    }
            }
            .padding(.top, item.topGap)
            .padding(.bottom, item.bottomGap)
        case .row:
            RowColumns(gap: metrics.columnGap) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(item.columns) { piece in
                        // report taps against the row, the unit the reader scrolls to
                        ReaderItemView(item: piece, metrics: metrics, selection: selection,
                                       onTapToken: { token, _, y in onTapToken(token, item, y) },
                                       onTapBackground: onTapBackground)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                Group {
                    if !item.rowCompanion.isEmpty {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(item.rowCompanion) { piece in
                                ReaderItemView(item: piece, metrics: metrics, selection: selection,
                                               onTapToken: { token, _, y in onTapToken(token, piece, y) },
                                               onTapBackground: onTapBackground)
                            }
                        }
                    } else if let english = item.rowEnglish, english.string.length > 0 {
                        GreekTextView(content: english, onTapBackground: onTapBackground)
                            .padding(.horizontal, metrics.englishInnerHorizontal)
                            .padding(.vertical, metrics.englishInnerVertical)
                            .background(Color(Palette.englishBackground))
                            .contentShape(Rectangle())
                            .onTapGesture(perform: onTapBackground)
                    } else {
                        Color.clear.frame(height: 1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .padding(.top, item.topGap)
            .padding(.bottom, item.bottomGap)
        case .heading, .speaker:
            GreekTextView(content: item.content, onTapBackground: onTapBackground)
                .padding(.leading, metrics.textInset)
                .padding(.top, item.topGap)
                .padding(.bottom, item.bottomGap)
        case .english:
            GreekTextView(content: item.content, onTapBackground: onTapBackground)
                .padding(.horizontal, metrics.englishInnerHorizontal)
                .padding(.vertical, metrics.englishInnerVertical)
                .background(
                    HStack(spacing: 0) {
                        Rectangle().fill(Color(Palette.muted).opacity(0.5)).frame(width: 2)
                        Rectangle().fill(Color(Palette.englishBackground))
                    }
                )
                .contentShape(Rectangle())
                .onTapGesture(perform: onTapBackground)
                .padding(.leading, metrics.textInset)
                .padding(.top, item.topGap)
                .padding(.bottom, item.bottomGap)
        }
    }
}

/// Small numbers in the left margin, baseline-aligned with the Greek first line.
struct NumberGutter: View {
    let label: String
    let metrics: ReaderMetrics

    var body: some View {
        let numberFont = UIFont.monospacedDigitSystemFont(ofSize: metrics.numberFontSize, weight: .regular)
        Text(label)
            .font(Font(numberFont as CTFont))
            .foregroundStyle(Color(Palette.muted))
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .frame(width: metrics.gutterWidth, alignment: .trailing)
            .padding(.top, max(0, metrics.textFont.ascender - numberFont.ascender))
            .contentShape(Rectangle())
    }
}
