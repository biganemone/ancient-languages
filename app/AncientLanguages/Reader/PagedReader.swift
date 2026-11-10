import SwiftUI
import UIKit

struct ReaderPage: Identifiable {
    let id: Int
    let items: [ReaderItem]
    let citation: String

    var anchor: ReaderAnchor? {
        items.first.map { ReaderAnchor(baseID: $0.baseID, location: $0.startLocation) }
    }
    // Rows (side by side) have no text of their own; a row cut across pages
    // is numbered piece 0, 1, … in `startLocation`, so each piece holds one
    // position.

    func contains(_ anchor: ReaderAnchor) -> Bool {
        items.contains { item in
            item.baseID == anchor.baseID && anchor.location >= item.startLocation
                && anchor.location < item.startLocation + max(item.content.string.length, 1)
        }
    }
}

/// Fills screen-sized pages with reader items, measuring each with TextKit at
/// the width it will be drawn. Verse lines are never split; a speech or an
/// English block that runs over the bottom is cut at a line boundary.
enum Paginator {
    static func paginate(_ items: [ReaderItem], metrics: ReaderMetrics, size: CGSize) -> [ReaderPage] {
        guard size.width > 50, size.height > 50 else { return [] }
        let height = size.height - 6   // slack for SwiftUI rounding row heights
        var pages: [[ReaderItem]] = []
        var current: [ReaderItem] = []
        var used: CGFloat = 0

        func close() {
            if !current.isEmpty { pages.append(current) }
            current = []
            used = 0
        }
        func width(_ item: ReaderItem) -> CGFloat {
            item.kind == .english ? metrics.englishTextWidth(contentWidth: size.width)
                                  : metrics.greekTextWidth(contentWidth: size.width)
        }
        func inner(_ item: ReaderItem) -> CGFloat {
            item.kind == .english ? 2 * metrics.englishInnerVertical : 0
        }
        func fullHeight(_ item: ReaderItem) -> CGFloat {
            let lines = ReaderText.lines(of: item.content.string, width: width(item))
            return item.topGap + inner(item) + ceil(lines.last?.maxY ?? 0) + item.bottomGap
        }

        for (i, item) in items.enumerated() {
            if item.kind == .row {
                var row = item
                while true {
                    if current.isEmpty { row.topGap = 0 }
                    let room = height - used - row.topGap
                    let (first, rest, firstHeight) = splitRow(row, room: room, metrics: metrics,
                                                              contentWidth: size.width, pageIsEmpty: current.isEmpty)
                    guard let first else {
                        close()          // nothing fits under what is already on this page
                        continue
                    }
                    current.append(first)
                    used += row.topGap + firstHeight
                    guard let rest else { break }
                    close()
                    row = rest
                }
                continue
            }
            // Greek with English blocks: a block's Greek and its English card
            // belong together. If the pair won't fit under what is already on
            // the page but would fit on a page of its own, start it on the next
            // page: a little less on this page rather than a card cut in two.
            // (The parallel text, Greek beside Latin or the reverse, counts as the translation.)
            if !current.isEmpty, !item.isTranslationSide, i == 0 || items[i - 1].isTranslationSide,
               var end = items[i..<min(items.count, i + 60)].firstIndex(where: { $0.isTranslationSide }) {
                while end + 1 < items.count, items[end + 1].isTranslationSide { end += 1 }
                let unit = items[i...end].reduce(CGFloat(0)) { $0 + fullHeight($1) }
                if used + unit > height, unit <= height {
                    close()
                }
            }
            var piece = item
            while true {
                if current.isEmpty { piece.topGap = 0 }
                let lines = ReaderText.lines(of: piece.content.string, width: width(piece))
                let textHeight = ceil(lines.last?.maxY ?? 0)
                let need = piece.topGap + inner(piece) + textHeight + piece.bottomGap
                // A heading or speaker name needs at least the first line of
                // what follows on the same page.
                var following: CGFloat = 0
                if piece.keepWithNext, i + 1 < items.count {
                    let next = items[i + 1]
                    let first = ReaderText.lines(of: next.content.string, width: width(next)).first?.maxY ?? 0
                    following = next.topGap + inner(next) + first
                }
                if used + need + (current.isEmpty ? 0 : following) <= height {
                    current.append(piece)
                    used += need
                    break
                }
                if piece.keepWithNext, !current.isEmpty {
                    close()
                    continue
                }
                let splittable = (piece.kind == .english || metrics.kind == .prose) && lines.count >= 2
                if splittable {
                    let room = height - used - piece.topGap - inner(piece)
                    let fitting = lines.prefix(while: { $0.maxY <= room }).count
                    // avoid a lone line at a page bottom; an English card is
                    // only cut if at least three lines stay on this page
                    let minimum = current.isEmpty ? 1 : (piece.kind == .english ? 3 : 2)
                    if fitting >= minimum, fitting < lines.count {
                        let cut = NSMaxRange(lines[fitting - 1].range)
                        let length = piece.content.string.length
                        let first = piece.with(content: piece.content.slice(NSRange(location: 0, length: cut)),
                                               startLocation: piece.startLocation, id: piece.id,
                                               gutterLabel: piece.gutterLabel, topGap: piece.topGap, bottomGap: 0)
                        current.append(first)
                        close()
                        piece = piece.with(content: piece.content.slice(NSRange(location: cut, length: length - cut)),
                                           startLocation: piece.startLocation + cut,
                                           id: piece.id + "+\(piece.startLocation + cut)",
                                           gutterLabel: "", topGap: 0, bottomGap: piece.bottomGap)
                        continue
                    }
                }
                if current.isEmpty {
                    // Taller than a page and can't be cut: give it a page of its own.
                    current.append(piece)
                    close()
                    break
                }
                close()
            }
        }
        close()

        return pages.enumerated().map { index, items in
            let cites = items.flatMap(\.greekCites)
            let citation: String
            if let first = cites.first, let last = cites.last, first != last {
                citation = "\(first)–\(last)"
            } else {
                citation = cites.first ?? items.first?.cite ?? ""
            }
            return ReaderPage(id: index, items: items, citation: citation)
        }
    }
}

extension Paginator {
    /// Fits as much of a side-by-side row as `room` allows. Returns the piece
    /// for this page (nil if nothing fits and the page already has content),
    /// the rest (nil if the row is done), and the height of the piece.
    ///
    /// The Greek column is filled item by item (prose cut at a line, verse
    /// lines kept whole). The English is cut in proportion, at a line, so the
    /// two columns stay roughly in step; it may run on into the next piece
    /// alone if it is the longer of the two.
    static func splitRow(_ row: ReaderItem, room: CGFloat, metrics: ReaderMetrics,
                         contentWidth: CGFloat, pageIsEmpty: Bool)
        -> (first: ReaderItem?, rest: ReaderItem?, height: CGFloat) {
        let columns = metrics.columnWidths(contentWidth: contentWidth)
        let greekWidth = metrics.greekTextWidth(contentWidth: columns.greek)
        let englishWidth = columns.english - 2 * metrics.englishInnerHorizontal
        let pad = 2 * metrics.englishInnerVertical

        func need(_ item: ReaderItem, isFirst: Bool) -> (CGFloat, [ReaderText.Line]) {
            let lines = ReaderText.lines(of: item.content.string, width: greekWidth)
            return ((isFirst ? 0 : item.topGap) + ceil(lines.last?.maxY ?? 0) + item.bottomGap, lines)
        }
        let english = row.rowEnglish ?? .empty
        let englishLines = english.string.length > 0 ? ReaderText.lines(of: english.string, width: englishWidth) : []
        let englishHeight = englishLines.isEmpty ? 0 : ceil(englishLines.last!.maxY) + pad
        let greekHeights = row.columns.indices.map { need(row.columns[$0], isFirst: $0 == 0).0 }
        let greekHeight = greekHeights.reduce(0, +)

        // With a parallel text (verse by verse, so short): the row is not cut;
        // it moves to the next page if it doesn't fit.
        if !row.rowCompanion.isEmpty {
            let width = metrics.greekTextWidth(contentWidth: columns.english)
            var right: CGFloat = 0
            for (i, item) in row.rowCompanion.enumerated() {
                let lines = ReaderText.lines(of: item.content.string, width: width)
                right += (i == 0 ? 0 : item.topGap) + ceil(lines.last?.maxY ?? 0) + item.bottomGap
            }
            let h = max(greekHeight, right)
            if h <= room || pageIsEmpty { return (row, nil, h) }
            return (nil, row, 0)
        }

        // The whole row fits.
        if max(greekHeight, englishHeight) <= room {
            return (row, nil, max(greekHeight, englishHeight))
        }

        // Greek: whole items while they fit, then part of a prose item.
        var taken: [ReaderItem] = []
        var left: [ReaderItem] = []
        var usedGreek: CGFloat = 0
        for item in row.columns {
            if !left.isEmpty { left.append(item); continue }
            let (h, lines) = need(item, isFirst: taken.isEmpty)
            if usedGreek + h <= room {
                var placed = item
                if taken.isEmpty { placed.topGap = 0 }
                taken.append(placed)
                usedGreek += h
                continue
            }
            let gap = taken.isEmpty ? 0 : item.topGap
            let fitting = lines.prefix(while: { usedGreek + gap + $0.maxY <= room }).count
            if (item.kind == .greek && metrics.kind == .prose) && fitting >= 1 && fitting < lines.count {
                let cut = NSMaxRange(lines[fitting - 1].range)
                let length = item.content.string.length
                taken.append(item.with(content: item.content.slice(NSRange(location: 0, length: cut)),
                                       startLocation: item.startLocation, id: item.id,
                                       gutterLabel: item.gutterLabel, topGap: gap, bottomGap: 0))
                usedGreek += gap + ceil(lines[fitting - 1].maxY)
                left.append(item.with(content: item.content.slice(NSRange(location: cut, length: length - cut)),
                                      startLocation: item.startLocation + cut,
                                      id: item.id + "+\(item.startLocation + cut)",
                                      gutterLabel: "", topGap: 0, bottomGap: item.bottomGap))
            } else {
                left.append(item)
            }
        }
        if taken.isEmpty && !row.columns.isEmpty {
            guard pageIsEmpty else { return (nil, row, 0) }
            // A single item taller than a page: give it the page anyway.
            taken = [row.columns[0]]
            left = Array(row.columns.dropFirst())
            usedGreek = greekHeights[0]
        }

        // English: in step with the Greek, but never past the bottom.
        let share = greekHeight > 0 ? usedGreek / greekHeight : 1
        let fittingEnglish = englishLines.prefix(while: { $0.maxY + pad <= room }).count
        var englishCount = left.isEmpty ? fittingEnglish
                                        : min(fittingEnglish, Int((share * CGFloat(englishLines.count)).rounded()))
        if taken.isEmpty && englishCount == 0 && !englishLines.isEmpty {
            guard pageIsEmpty else { return (nil, row, 0) }
            englishCount = max(1, fittingEnglish)
        }
        var englishFirst: ReaderText.Content = .empty
        var englishRest: ReaderText.Content = .empty
        if englishCount > 0 {
            let cut = englishCount >= englishLines.count ? english.string.length
                                                         : NSMaxRange(englishLines[englishCount - 1].range)
            englishFirst = english.slice(NSRange(location: 0, length: cut))
            englishRest = english.slice(NSRange(location: cut, length: english.string.length - cut))
        } else {
            englishRest = english
        }
        let englishUsed = englishCount > 0 ? ceil(englishLines[englishCount - 1].maxY) + pad : 0

        // Only a line or two would fit at the bottom of a page that already has
        // text: start the row on the next page instead.
        let minimumPiece = 3 * (metrics.textFont.lineHeight + ReaderText.lineSpacing(metrics.textFontSize))
        if !pageIsEmpty, max(usedGreek, englishUsed) < minimumPiece {
            return (nil, row, 0)
        }

        var first = row
        first.columns = taken
        first.rowEnglish = englishFirst
        first.bottomGap = 0
        guard !left.isEmpty || englishRest.string.length > 0 else {
            return (first, nil, max(usedGreek, englishUsed))
        }
        var rest = row
        if !left.isEmpty { left[0].topGap = 0 }
        rest.columns = left
        rest.rowEnglish = englishRest
        rest.topGap = 0
        rest = rest.renumbered(row.startLocation + 1)
        return (first, rest, max(usedGreek, englishUsed))
    }
}

/// Reading by pages: swipe sideways to turn. The page geometry ignores the
/// navigation bar (which just overlays the top margin), so hiding the chrome
/// never re-flows the text. `anchor` is two-way: turning pages updates it,
/// and setting it from outside (Go to…) turns to the page that holds it.
struct PagedReaderView: View {
    let items: [ReaderItem]
    let itemsVersion: Int
    let metrics: ReaderMetrics
    let selection: WordSelection?
    let chromeHidden: Bool
    /// No-bars reading: the page uses the room the navigation bar and footer
    /// would take (repaginating on the way in and out, keeping the place).
    var fullPage: Bool = false
    /// The faint hide-bars button sits in the bottom margin; leave it room.
    var cornerButton: Bool = true
    @Binding var anchor: ReaderAnchor?
    /// Text for the footer's right side, e.g. "Book 3".
    var partLabel: String = ""
    /// Called when the reader swipes past the last page / before the first.
    var onNextPart: (() -> Void)?
    var onPreviousPart: (() -> Void)?
    let onTapToken: (Token, ReaderItem, CGFloat) -> Void
    let onTapBackground: () -> Void

    @State private var pages: [ReaderPage] = []
    @State private var index = 0
    /// Bumped shortly after the size changes (rotation): the window's safe
    /// area, which sets the page margins, is only final once the rotation
    /// has finished, so the page frame is measured again then.
    @State private var settledPass = 0
    /// Bumped when a new list of items (another book, chapter, layout) has been
    /// paginated: the paged TabView is then made afresh, already on the right
    /// page. Changing its pages and its selection at once leaves a page-style
    /// TabView showing the old position (the "Next book" spinner) until the
    /// reader swipes away and back.
    @State private var tabGeneration = 0
    @State private var paginatedVersion = -1

    // Measured, not assumed (the page margins were off by a line or two, differently
    // from text to text and with the bars shown or hidden):
    /// Where the navigation bar ends (the top of the safe area, with the bars shown).
    @State private var barsTop: CGFloat = 0
    /// How far the text actually lands from where the page frame puts it: the pages
    /// are moved by the difference.
    @State private var topShift: CGFloat = 0
    /// How much taller than the page the text came out (it ran under the footer):
    /// pages are made this much shorter and paginated again.
    @State private var shrink: CGFloat = 0
    @State private var shrinkScope = ""
    /// Shrinking is tried at most a few times per page size, and one at a time, so
    /// that measuring can never keep the reader repaginating.
    @State private var shrinkSteps = 0
    @State private var shrinkPending = false

    private struct Key: Hashable {
        let version: Int
        let metrics: ReaderMetrics
        let width: CGFloat
        let height: CGFloat
        let pass: Int
        let full: Bool
        let corner: Bool
        let barsTop: CGFloat
        let shrink: CGFloat
    }

    var body: some View {
        ZStack {
            // The safe area as laid out (below the navigation bar when it shows).
            GeometryReader { probe in
                Color.clear
                    .onAppear { noteBarsTop(probe.frame(in: .global).minY) }
                    .onChange(of: probe.frame(in: .global).minY) { _, y in noteBarsTop(y) }
            }
            pager
        }
    }

    private var pager: some View {
        GeometryReader { geo in
            let frame = PageFrame(size: geo.size, metrics: metrics, full: fullPage, cornerButton: cornerButton,
                                  barsTop: barsTop)
            ZStack(alignment: .bottom) {
                Color(Palette.paper)
                    .contentShape(Rectangle())
                    .onTapGesture(perform: onTapBackground)
                TabView(selection: $index) {
                    // Each page ignores the safe area itself: a page-style TabView gives its
                    // pages the safe area again even when the TabView ignores it, which
                    // pushed the text down by the status-bar height (empty lines at the
                    // top, the last lines under the footer) on full pages.
                    if onPreviousPart != nil {
                        partTurn(previous: true).ignoresSafeArea().tag(-1)
                    }
                    ForEach(pages) { page in
                        pageView(page, frame: frame).ignoresSafeArea().tag(page.id)
                    }
                    if onNextPart != nil {
                        partTurn(previous: false).ignoresSafeArea().tag(pages.count)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .id(tabGeneration)
                .ignoresSafeArea()
                footer
                    .padding(.bottom, frame.footerBottom)
                    .opacity(chromeHidden ? 0 : 1)
                    .allowsHitTesting(false)
            }
            .task(id: Key(version: itemsVersion, metrics: metrics, width: geo.size.width, height: geo.size.height,
                          pass: settledPass, full: fullPage, corner: cornerButton, barsTop: barsTop, shrink: shrink)) {
                let scope = "\(metrics.hashValue)|\(geo.size.width)|\(geo.size.height)|\(fullPage)|\(barsTop)"
                if scope != shrinkScope {          // a new page size or type: measure afresh
                    shrinkScope = scope
                    shrinkSteps = 0
                    if shrink != 0 { shrink = 0; return }
                }
                repaginate(frame: frame)
            }
            .onChange(of: geo.size) { _, _ in
                Task {
                    try? await Task.sleep(for: .milliseconds(450))
                    settledPass += 1
                }
            }
        }
        .ignoresSafeArea()
        .onChange(of: index) { _, newValue in
            if newValue == -1, let onPreviousPart {
                onPreviousPart()
            } else if newValue == pages.count, !pages.isEmpty, let onNextPart {
                onNextPart()
            } else if pages.indices.contains(newValue) {
                anchor = pages[newValue].anchor
            }
        }
        .onChange(of: anchor) { _, newValue in
            // A jump requested from outside (Go to…).
            guard let newValue, pages.indices.contains(index), !pages[index].contains(newValue),
                  let found = pages.firstIndex(where: { $0.contains(newValue) }) else { return }
            index = found
        }
    }

    private func pageView(_ page: ReaderPage, frame: PageFrame) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(page.items) { item in
                    ReaderItemView(item: item, metrics: metrics, selection: selection,
                                   onTapToken: onTapToken, onTapBackground: onTapBackground)
                }
            }
            .fixedSize(horizontal: false, vertical: true)   // its natural height, even when too tall
            // how tall the text really came out
            .background(GeometryReader { g in
                Color.clear
                    .onAppear { measuredHeight(page, frame: frame, height: g.size.height) }
                    .onChange(of: g.size.height) { _, h in measuredHeight(page, frame: frame, height: h) }
            })
            Color.clear
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
                .onTapGesture(perform: onTapBackground)
        }
        .frame(width: frame.contentSize.width, height: frame.contentSize.height, alignment: .top)
        .padding(.top, frame.top)
        .padding(.leading, frame.leading)
        .offset(y: topShift)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        // Where the page itself sits (it should be at the top of the screen). Measured
        // outside the offset, so moving the text doesn't change the measurement.
        .background(GeometryReader { g in
            Color.clear
                .onAppear { measuredPageTop(page, g.frame(in: .global).minY) }
                .onChange(of: g.frame(in: .global).minY) { _, y in measuredPageTop(page, y) }
        })
        // Taps in the margins (behind the text views) toggle the chrome.
        .background(Color.clear.contentShape(Rectangle()).onTapGesture(perform: onTapBackground))
    }

    /// A page shown briefly while moving to the next/previous book.
    private func partTurn(previous: Bool) -> some View {
        VStack(spacing: 8) {
            ProgressView()
            Text(previous ? "Previous book" : "Next book")
                .font(.footnote).foregroundStyle(Color(Palette.muted))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var footer: some View {
        let page = pages.indices.contains(index) ? pages[index] : nil
        return HStack(spacing: 12) {
            Text(page?.citation ?? "")
            Text(pages.isEmpty ? "" : "\(min(index, pages.count - 1) + 1) / \(pages.count)")
            if !partLabel.isEmpty { Text(partLabel) }
        }
        .font(.caption2.monospacedDigit())
        .foregroundStyle(Color(Palette.muted))
    }

    /// The navigation bar's bottom, read while the bars show (not while they are
    /// hidden for reading, nor in no-bars mode, where it isn't used).
    private func noteBarsTop(_ y: CGFloat) {
        guard !chromeHidden, !fullPage, y > 0, abs(y - barsTop) > 0.5 else { return }
        Task {
            try? await Task.sleep(for: .milliseconds(350))     // let the bars finish moving
            if !chromeHidden, !fullPage, abs(y - barsTop) > 0.5 { barsTop = y }
        }
    }

    /// A page placed below the top of the screen (the page-style TabView sometimes
    /// keeps the safe area for its pages): the text is moved up by as much.
    private func measuredPageTop(_ page: ReaderPage, _ y: CGFloat) {
        guard page.id == index, y.isFinite, abs(y) < 120 else { return }
        if abs(-y - topShift) > 1 { topShift = -y }
    }

    /// Text that came out taller than the page (it ran under the footer): the pages
    /// are laid out again a little shorter, at most three times per page size.
    private func measuredHeight(_ page: ReaderPage, frame: PageFrame, height: CGFloat) {
        let limit = frame.contentSize.height / 4
        let over = height - frame.contentSize.height
        guard page.id == index, page.items.count > 1, over > 0.5, !shrinkPending,
              shrinkSteps < 3, shrink < limit else { return }
        shrinkPending = true
        Task {
            try? await Task.sleep(for: .milliseconds(250))    // let the page settle first
            shrinkSteps += 1
            shrink = min(shrink + over + 2, limit)
            shrinkPending = false
        }
    }

    private func repaginate(frame: PageFrame) {
        let keep = anchor
        let size = CGSize(width: frame.contentSize.width, height: frame.contentSize.height - shrink)
        pages = Paginator.paginate(items, metrics: metrics, size: size)
        if let keep, let found = pages.firstIndex(where: { $0.contains(keep) })
            ?? pages.firstIndex(where: { $0.items.contains { $0.baseID == keep.baseID } }) {
            // (the second: a row cut differently at a new size)
            index = found
        } else {
            index = 0
        }
        if pages.indices.contains(index) { anchor = pages[index].anchor }
        if itemsVersion != paginatedVersion {
            paginatedVersion = itemsVersion
            tabGeneration += 1
        }
    }
}

extension PageFrame {
    /// A home-indicator strip at the bottom of the screen (Face ID iPhones), not a Home button.
    static func hasHomeStrip(_ insets: UIEdgeInsets) -> Bool { insets.bottom >= 20 }

    /// The key window's safe area (what the page margins are measured from).
    static var windowInsets: UIEdgeInsets {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow)?.safeAreaInsets ?? .zero
    }

    /// How far above the bottom edge of the screen the footer line sits.
    var footerBottom: CGFloat {
        Self.hasHomeStrip(insets) ? insets.bottom - 20 : insets.bottom + 6
    }
}

/// Page margins: the window's safe area (which doesn't change when the bars
/// hide, on Face ID devices) plus room for the navigation bar and the footer.
struct PageFrame {
    let insets: UIEdgeInsets
    let top: CGFloat
    let leading: CGFloat
    let contentSize: CGSize

    init(size: CGSize, metrics: ReaderMetrics, full: Bool = false, cornerButton: Bool = true, barsTop: CGFloat = 0) {
        let window = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow)
        var insets = window?.safeAreaInsets ?? .zero
        insets.top = max(insets.top, 20)          // status bar on Home-button devices
        self.insets = insets
        // With the bars showing: room for the navigation bar above and the
        // footer line (and the hide-bars button) below. With no bars, only a
        // small margin, plus the button's corner if it is shown.
        // On Face ID iPhones the footer (and the hide-bars button) sit low, in
        // the home-indicator strip where the screen curves, so the text can
        // run nearly to the bottom of the safe area.
        let navigationBar: CGFloat = full ? 0 : 44
        let footer: CGFloat
        if Self.hasHomeStrip(insets) {
            footer = 8
        } else {
            footer = full ? (cornerButton ? 34 : 12) : 36
        }
        // the navigation bar's real bottom when it has been measured
        top = !full && barsTop > insets.top ? barsTop + 4 : insets.top + navigationBar + (full ? 6 : 2)
        leading = insets.left + metrics.leadingPadding
        let width = size.width - insets.left - insets.right - metrics.leadingPadding - metrics.trailingPadding
        let height = size.height - top - insets.bottom - footer
        contentSize = CGSize(width: max(width, 0), height: max(height, 0))
    }
}
