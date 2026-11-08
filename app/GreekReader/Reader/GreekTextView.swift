import SwiftUI
import UIKit

/// Draws a piece of reader text (a verse line, a speech, or an English block)
/// with TextKit, so we get a real hanging indent (wrapped continuation lines
/// sit indented under the first) and exact word hit-testing. SwiftUI's Text
/// can do neither. The content is built by `ReaderText`.
struct GreekTextView: UIViewRepresentable {
    let content: ReaderText.Content
    /// The selected word, if any. Both pieces of a word broken across lines
    /// are highlighted.
    var highlighted: Token?
    /// Highlights and notes (and a selection being made), by token row id.
    var marks: [Int: TokenMark] = [:]
    /// A long press on a word starts a highlight.
    var onLongPressToken: ((Token) -> Void)? = nil
    /// Called with the tapped word and the tap's vertical position as a
    /// fraction of the window height (so the reader can keep it visible).
    var onTapToken: (Token, CGFloat) -> Void = { _, _ in }
    let onTapBackground: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView(usingTextLayoutManager: false)   // TextKit 1, same as ReaderText.lines
        view.isEditable = false
        view.isSelectable = false
        view.isScrollEnabled = false
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.addGestureRecognizer(UITapGestureRecognizer(target: context.coordinator,
                                                         action: #selector(Coordinator.tapped(_:))))
        let press = UILongPressGestureRecognizer(target: context.coordinator,
                                                 action: #selector(Coordinator.pressed(_:)))
        press.minimumPressDuration = 0.4
        view.addGestureRecognizer(press)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        let c = context.coordinator
        c.tokens = content.tokens
        c.ranges = content.tokenRanges
        c.onTapToken = onTapToken
        c.onTapBackground = onTapBackground
        c.onLongPressToken = onLongPressToken

        var string = content.string
        if !marks.isEmpty {
            string = Self.paint(string, content: content, marks: marks)
        }
        if let h = highlighted {
            let hits = content.tokens.indices.filter {
                content.tokens[$0].isSameWord(as: h) && NSMaxRange(content.tokenRanges[$0]) <= string.length
            }
            if !hits.isEmpty {
                let marked = NSMutableAttributedString(attributedString: string)
                for i in hits {
                    marked.addAttribute(.backgroundColor, value: Palette.highlight, range: content.tokenRanges[i])
                }
                string = marked
            }
        }
        if view.attributedText != string {
            view.attributedText = string
        }
    }

    /// Highlight backgrounds (joined across the spaces between words of the
    /// same highlight) and a dotted underline where there is a note. Neither
    /// changes the layout, so pagination is unaffected.
    private static func paint(_ string: NSAttributedString, content: ReaderText.Content,
                              marks: [Int: TokenMark]) -> NSAttributedString {
        let marked = NSMutableAttributedString(attributedString: string)
        let length = marked.length
        var previous: (mark: TokenMark, end: Int)?
        for (token, range) in zip(content.tokens, content.tokenRanges) {
            guard let mark = marks[token.id], NSMaxRange(range) <= length else {
                previous = nil
                continue
            }
            var paint = range
            if let previous, previous.mark.owner == mark.owner, previous.end <= range.location {
                paint = NSRange(location: previous.end, length: NSMaxRange(range) - previous.end)
            }
            marked.addAttribute(.backgroundColor, value: mark.color, range: paint)
            if mark.hasNote {
                marked.addAttributes([
                    .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                    .underlineColor: Palette.speaker,
                ], range: paint)
            }
            previous = (mark, NSMaxRange(range))
        }
        return marked
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        let fitted = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        return CGSize(width: width, height: ceil(fitted.height))
    }

    final class Coordinator: NSObject {
        var tokens: [Token] = []
        var ranges: [NSRange] = []
        var onTapToken: ((Token, CGFloat) -> Void)?
        var onTapBackground: (() -> Void)?
        var onLongPressToken: ((Token) -> Void)?

        @objc func pressed(_ gesture: UILongPressGestureRecognizer) {
            guard gesture.state == .began, let view = gesture.view as? UITextView,
                  let i = tokenIndex(at: gesture.location(in: view), in: view) else { return }
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            onLongPressToken?(tokens[i])
        }

        @objc func tapped(_ gesture: UITapGestureRecognizer) {
            guard let view = gesture.view as? UITextView else { return }
            if let i = tokenIndex(at: gesture.location(in: view), in: view) {
                let windowY = gesture.location(in: nil).y
                let height = view.window?.bounds.height ?? 1
                onTapToken?(tokens[i], windowY / max(height, 1))
            } else {
                onTapBackground?()
            }
        }

        /// The nearest word whose box (slightly enlarged) contains the point,
        /// so a tap that lands in the gap between words still finds one.
        func tokenIndex(at location: CGPoint, in view: UITextView) -> Int? {
            let layout = view.layoutManager
            let container = view.textContainer
            let length = view.attributedText?.length ?? 0
            var point = location
            point.x -= view.textContainerInset.left
            point.y -= view.textContainerInset.top
            var best: (index: Int, distance: CGFloat)?
            for (i, range) in ranges.enumerated() where NSMaxRange(range) <= length {
                let glyphs = layout.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
                let box = layout.boundingRect(forGlyphRange: glyphs, in: container)
                guard box.insetBy(dx: -6, dy: -4).contains(point) else { continue }
                let distance = abs(point.x - box.midX) + abs(point.y - box.midY)
                if best == nil || distance < best!.distance { best = (i, distance) }
            }
            return best?.index
        }
    }
}
