import UIKit

/// Builds the attributed strings the reader displays, and the shared layout
/// metrics. Both the scrolling reader and the paginator use these, so what
/// the paginator measures is exactly what the text views draw.
enum ReaderText {
    /// Display text plus the display ranges of its words.
    struct Content {
        let string: NSAttributedString
        let tokens: [Token]
        let tokenRanges: [NSRange]

        static let empty = Content(string: NSAttributedString(), tokens: [], tokenRanges: [])

        /// A piece of this content (used when a speech or English block runs
        /// over a page break). Words outside the range are dropped.
        func slice(_ range: NSRange) -> Content {
            var kept: [Token] = []
            var ranges: [NSRange] = []
            for (token, r) in zip(tokens, tokenRanges) where NSIntersectionRange(r, range).length == r.length {
                kept.append(token)
                ranges.append(NSRange(location: r.location - range.location, length: r.length))
            }
            return Content(string: string.attributedSubstring(from: range), tokens: kept, tokenRanges: ranges)
        }
    }

    /// Display-only text spliced into the Greek (speaker labels, inline
    /// Stephanus numbers). Offsets are UTF-16 positions in the segment text.
    struct Insertion {
        enum Style { case speaker, marker }
        let offset: Int
        let text: String
        let style: Style
    }

    static func lineSpacing(_ fontSize: CGFloat) -> CGFloat { fontSize * 0.28 }

    /// `firstLineIndent` pushes the first line right: used for the second
    /// half of a verse line shared between two speakers.
    /// `rtl`: Hebrew, laid out right to left (indents mirror). `hideMarks`:
    /// Hebrew cantillation drawn invisibly (kept in the text, so word offsets
    /// stay right).
    static func greek(_ text: String, tokens: [Token], insertions: [Insertion] = [],
                      fontSize: CGFloat, hangingIndent: CGFloat, firstLineIndent: CGFloat = 0,
                      coptic: Bool = false, rtl: Bool = false, hideMarks: Bool = false,
                      devanagari: Bool = false) -> Content {
        // Sanskrit in Devanāgarī: transliterate, and carry word and insertion
        // offsets (stored against the IAST) over to the new text
        var text = text
        var map: [Int]? = nil
        var insertions = insertions
        if devanagari {
            let d = Devanagari.transliterate(text)
            text = d.text
            map = d.map
            insertions = insertions.map {
                Insertion(offset: d.map[min(max($0.offset, 0), d.map.count - 1)], text: $0.text, style: $0.style)
            }
        }
        func shown(_ offset: Int) -> Int {
            guard let map else { return offset }
            return map[min(max(offset, 0), map.count - 1)]
        }
        let paragraph = NSMutableParagraphStyle()
        paragraph.baseWritingDirection = rtl ? .rightToLeft : .natural
        paragraph.firstLineHeadIndent = firstLineIndent
        paragraph.headIndent = hangingIndent
        paragraph.lineSpacing = lineSpacing(fontSize)
        paragraph.lineBreakMode = .byWordWrapping

        let base: [NSAttributedString.Key: Any] = [
            .font: Fonts.text(size: fontSize, coptic: coptic),
            .foregroundColor: Palette.ink,
            .paragraphStyle: paragraph,
        ]
        let source = text as NSString
        let result = NSMutableAttributedString()
        var cursor = 0
        var shifts: [(offset: Int, length: Int)] = []

        for insertion in insertions.sorted(by: { $0.offset < $1.offset }) {
            let at = min(max(insertion.offset, cursor), source.length)
            result.append(NSAttributedString(
                string: source.substring(with: NSRange(location: cursor, length: at - cursor)), attributes: base))
            var attrs = base
            switch insertion.style {
            case .speaker:
                attrs[.font] = Fonts.greekBold(size: fontSize * 0.8)
                attrs[.foregroundColor] = Palette.speaker
            case .marker:
                attrs[.font] = UIFont.monospacedDigitSystemFont(ofSize: fontSize * 0.55, weight: .regular)
                attrs[.foregroundColor] = Palette.muted
                attrs[.baselineOffset] = fontSize * 0.25
            }
            let piece = NSAttributedString(string: insertion.text, attributes: attrs)
            result.append(piece)
            shifts.append((at, piece.length))
            cursor = at
        }
        result.append(NSAttributedString(string: source.substring(from: cursor), attributes: base))

        if hideMarks {
            let ns = result.string as NSString
            for i in 0..<ns.length {
                let c = ns.character(at: i)
                if (0x0591...0x05AF).contains(c) || c == 0x05BD {
                    result.addAttribute(.foregroundColor, value: UIColor.clear, range: NSRange(location: i, length: 1))
                }
            }
        }
        // Insertions never fall inside a word, so each word just shifts.
        let ranges = tokens.map { token -> NSRange in
            let start = shown(token.start), end = shown(token.end)
            let shift = shifts.filter { $0.offset <= start }.reduce(0) { $0 + $1.length }
            return NSRange(location: start + shift, length: max(0, end - start))
        }
        return Content(string: result, tokens: tokens, tokenRanges: ranges)
    }

    /// Joins two pieces of content (prose paragraphs continued across a
    /// section break), with optional display-only text between them.
    static func join(_ a: Content, _ separator: NSAttributedString?, _ b: Content) -> Content {
        let result = NSMutableAttributedString(attributedString: a.string)
        if let separator { result.append(separator) }
        let shift = result.length
        result.append(b.string)
        let ranges = a.tokenRanges + b.tokenRanges.map { NSRange(location: $0.location + shift, length: $0.length) }
        return Content(string: result, tokens: a.tokens + b.tokens, tokenRanges: ranges)
    }

    /// A small inline Stephanus number, as used inside running prose.
    static func inlineMarker(_ label: String, fontSize: CGFloat) -> NSAttributedString {
        NSAttributedString(string: " \u{2009}\(label)\u{2009}", attributes: [
            .font: UIFont.monospacedDigitSystemFont(ofSize: fontSize * 0.55, weight: .regular),
            .foregroundColor: Palette.muted,
            .baselineOffset: fontSize * 0.25,
        ])
    }

    /// Book titles ("Book 2") and lyric labels ("strophe 1").
    static func heading(_ text: String, fontSize: CGFloat, major: Bool) -> Content {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = major ? .center : .natural
        let attrs: [NSAttributedString.Key: Any] = major
            ? [.font: UIFont.systemFont(ofSize: fontSize * 0.75, weight: .semibold),
               .foregroundColor: Palette.speaker, .kern: fontSize * 0.08, .paragraphStyle: paragraph]
            : [.font: UIFont.italicSystemFont(ofSize: fontSize * 0.6),
               .foregroundColor: Palette.muted, .paragraphStyle: paragraph]
        let shown = major ? text.uppercased() : text
        return Content(string: NSAttributedString(string: shown, attributes: attrs), tokens: [], tokenRanges: [])
    }

    /// A speaker's name above a speech in drama.
    static func speaker(_ name: String, fontSize: CGFloat) -> Content {
        let attrs: [NSAttributedString.Key: Any] = [
            .font: Fonts.greekBold(size: fontSize * 0.72),
            .foregroundColor: Palette.speaker,
        ]
        return Content(string: NSAttributedString(string: name, attributes: attrs), tokens: [], tokenRanges: [])
    }

    static func english(_ text: String, fontSize: CGFloat) -> Content {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = fontSize * 0.12
        paragraph.paragraphSpacing = fontSize * 0.4
        let attrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: fontSize * 0.74),
            .foregroundColor: Palette.ink.withAlphaComponent(0.78),
            .paragraphStyle: paragraph,
        ]
        return Content(string: NSAttributedString(string: text, attributes: attrs), tokens: [], tokenRanges: [])
    }

    // MARK: - Measuring

    struct Line {
        let range: NSRange   // characters on this visual line
        let maxY: CGFloat    // bottom of the line, from the top of the text
    }

    /// Lays the string out at `width` with the same TextKit 1 settings as the
    /// on-screen text views (no insets, no line-fragment padding).
    static func lines(of string: NSAttributedString, width: CGFloat) -> [Line] {
        let storage = NSTextStorage(attributedString: string)
        let layout = NSLayoutManager()
        let container = NSTextContainer(size: CGSize(width: width, height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0
        layout.addTextContainer(container)
        storage.addLayoutManager(layout)
        layout.ensureLayout(for: container)

        var result: [Line] = []
        let glyphs = layout.glyphRange(for: container)
        layout.enumerateLineFragments(forGlyphRange: glyphs) { rect, _, _, glyphRange, _ in
            // The fragment rect includes line spacing, so this is conservative.
            let chars = layout.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil)
            result.append(Line(range: chars, maxY: rect.maxY))
        }
        // usedRect(for:) also counts trailing line spacing, as UITextView does.
        if let last = result.last {
            let total = layout.usedRect(for: container).height
            result[result.count - 1] = Line(range: last.range, maxY: max(last.maxY, total))
        }
        return result
    }

    static func height(of string: NSAttributedString, width: CGFloat) -> CGFloat {
        ceil(lines(of: string, width: width).last?.maxY ?? 0)
    }
}

/// Spacing and widths shared by the views and the paginator.
struct ReaderMetrics: Hashable {
    let fontSize: CGFloat
    let showNumbers: Bool
    let kind: Work.Kind
    var coptic = false
    var rtl = false                 // Hebrew
    var hideCantillation = false
    var devanagari = false          // Sanskrit shown in Devanāgarī
    /// Hebrew text has its own size (pointed Hebrew wants a larger one); the
    /// English, numbers and spacing still follow `fontSize`.
    var hebrewFontSize: CGFloat = ReaderMetrics.defaultHebrewFontSize
    /// Devanāgarī likewise (IAST keeps `fontSize`).
    var devanagariFontSize: CGFloat = ReaderMetrics.defaultDevanagariFontSize
    static let defaultDevanagariFontSize: CGFloat = 26
    static let defaultHebrewFontSize: CGFloat = 26

    /// The size of the original-language text: Hebrew's own, else `fontSize`.
    var textFontSize: CGFloat { rtl ? hebrewFontSize : devanagari ? devanagariFontSize : fontSize }
    func textFontSize(hebrew: Bool) -> CGFloat { hebrew ? hebrewFontSize : fontSize }
    var textFont: UIFont { Fonts.text(size: textFontSize, coptic: coptic) }

    var leadingPadding: CGFloat { showNumbers ? 4 : 18 }
    let trailingPadding: CGFloat = 18
    var numberFontSize: CGFloat { max(11, fontSize * 0.55) }
    var gutterWidth: CGFloat { numberFontSize * 2.7 }
    var gutterSpacing: CGFloat { fontSize * 0.5 }
    /// Where the Greek text starts, measured from the content's leading edge.
    var textInset: CGFloat { showNumbers ? gutterWidth + gutterSpacing : 0 }
    var hangingIndent: CGFloat { kind == .verse ? fontSize * 1.3 : 0 }

    /// Space above a verse line that opens a paragraph in the edition.
    var verseParagraphGap: CGFloat { fontSize * 0.6 }
    /// Space between speeches in prose.
    var speechGap: CGFloat { fontSize * 0.6 }
    /// Outer space above/below an English block, and its inner padding.
    var englishOuterGap: CGFloat { fontSize * 0.45 }
    let englishInnerVertical: CGFloat = 8
    let englishInnerHorizontal: CGFloat = 10

    func greekTextWidth(contentWidth: CGFloat) -> CGFloat { contentWidth - textInset }

    /// Side by side (iPad): Greek and English columns with this space between
    /// them. The Greek gets the larger share; it carries the line numbers
    /// and is set in a bigger type.
    var columnGap: CGFloat { fontSize * 1.2 }
    static let greekColumnShare: CGFloat = 0.56
    func columnWidths(contentWidth: CGFloat) -> (greek: CGFloat, english: CGFloat) {
        let greek = ((contentWidth - columnGap) * Self.greekColumnShare).rounded(.down)
        return (greek, contentWidth - columnGap - greek)
    }
    func englishTextWidth(contentWidth: CGFloat) -> CGFloat {
        contentWidth - textInset - 2 * englishInnerHorizontal
    }
}
