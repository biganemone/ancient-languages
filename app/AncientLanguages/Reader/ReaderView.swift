import SwiftUI

/// A book of a long work (Iliad 1, Odyssey 9, Republic 1); short works have one part.
struct WorkPart: Identifiable, Hashable {
    let id: Int
    let key: String       // "1", "2", … or "" for a single-part work
    let label: String     // "Book 1"
    let blocks: [Block]
}

/// Reads one work, either by turning pages (default) or by scrolling.
struct ReaderView: View {
    let work: Work
    let library: Library

    @State private var parts: [WorkPart] = []
    @State private var partIndex = 0
    @State private var content = ReaderContent()
    @State private var itemsVersion = 0
    @State private var loadError: String?
    @State private var selection: WordSelection?
    @State private var showLookup = false
    @State private var showGoTo = false
    @State private var chromeHidden = false
    /// Reading with no bars at all, entered with the floating button. Unlike
    /// bars hidden by scrolling, it stays until the button (or a tap on blank
    /// space) brings them back.
    @State private var focusMode = false
    @State private var anchor: ReaderAnchor?
    @State private var startAtEnd = false
    @State private var copiedNote = false

    @AppStorage(SettingsKey.showNumbers) private var showNumbers = true
    @AppStorage(SettingsKey.fontSize) private var fontSize = 20.0
    @AppStorage(SettingsKey.hebrewFontSize) private var hebrewFontSize = Double(ReaderMetrics.defaultHebrewFontSize)
    @AppStorage(SettingsKey.devanagariFontSize) private var devanagariFontSize = Double(ReaderMetrics.defaultDevanagariFontSize)
    @AppStorage(SettingsKey.layout) private var layout = TranslationLayout.interleaved
    @AppStorage(SettingsKey.paged) private var paged = true
    @AppStorage(SettingsKey.positions) private var savedPositions = ""
    @AppStorage(SettingsKey.focusButton) private var showFocusButton = true
    @AppStorage(SettingsKey.hideCantillation) private var hideCantillation = false
    @AppStorage(SettingsKey.devanagari) private var devanagari = false
    @AppStorage(SettingsKey.parallel) private var parallelLanguage = ""

    /// Parallel texts (Vulgate ↔ LXX / Greek NT, Sahidic ↔ Greek NT), by
    /// language: each block's counterparts, and the works they belong to.
    struct Companion {
        var blocks: [Int: [Block]] = [:]
        var workOf: [Int: Work] = [:]
    }
    @State private var companions: [String: Companion] = [:]
    private var activeCompanion: Companion? { companions[parallelLanguage] }

    @Environment(\.openURL) private var openURL
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(AnnotationStore.self) private var store

    // Highlights and notes
    @State private var segmentIndex = SegmentIndex()
    @State private var rangeStart: Token?        // long-pressed word: choosing words to highlight
    @State private var rangeEnd: Token?
    @State private var editing: Annotation?      // note editor
    @State private var pendingEdit: Annotation?  // opened once another sheet has gone
    @State private var showAnnotations = false
    @State private var showCopticSigns = false

    private let lookupDetent = PresentationDetent.fraction(0.42)

    private var metrics: ReaderMetrics {
        ReaderMetrics(fontSize: fontSize, showNumbers: showNumbers, kind: work.kind, coptic: work.isCoptic,
                      rtl: work.isHebrew, hideCantillation: work.isHebrew && hideCantillation,
                      devanagari: work.isSanskrit && devanagari, hebrewFontSize: hebrewFontSize,
                      devanagariFontSize: devanagariFontSize)
    }

    /// Side by side needs a regular-width screen (iPad, not in a narrow split
    /// view); elsewhere it falls back to English blocks between the Greek.
    private var effectiveLayout: TranslationLayout {
        layout == .sideBySide && sizeClass != .regular ? .interleaved : layout
    }

    private var layoutChoices: [TranslationLayout] {
        TranslationLayout.allCases.filter { $0 != .sideBySide || sizeClass == .regular }
    }

    private var part: WorkPart? { parts.indices.contains(partIndex) ? parts[partIndex] : nil }

    private var nextPartAction: (() -> Void)? {
        guard partIndex + 1 < parts.count else { return nil }
        return { switchPart(partIndex + 1) }
    }

    private var previousPartAction: (() -> Void)? {
        guard partIndex > 0 else { return nil }
        return { switchPart(partIndex - 1, atEnd: true) }
    }

    /// Everything that changes the list of items (and so the pagination).
    private struct ItemsKey: Hashable {
        let parts: Int
        let part: Int
        let metrics: ReaderMetrics
        let layout: TranslationLayout
        let parallel: String
    }

    var body: some View {
        Group {
            if let loadError {
                Text(loadError).foregroundStyle(.red).padding()
            } else if paged {
                PagedReaderView(items: content.items, itemsVersion: itemsVersion, metrics: metrics,
                                selection: selection, chromeHidden: chromeHidden,
                                fullPage: focusMode, cornerButton: showFocusButton, anchor: $anchor,
                                partLabel: parts.count > 1 ? (part?.label ?? "") : "",
                                onNextPart: nextPartAction, onPreviousPart: previousPartAction,
                                onTapToken: select, onTapBackground: backgroundTapped)
            } else {
                scrollingReader
            }
        }
        .environment(\.readerAnnotations, annotationContext)
        .background(Color(Palette.paper).ignoresSafeArea())
        .navigationTitle(parts.count > 1 ? "\(work.title) · \(part?.label ?? "")" : work.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(chromeHidden ? .hidden : .visible, for: .navigationBar)
        .toolbarBackground(Color(Palette.paper), for: .navigationBar)
        .statusBarHidden(chromeHidden)
        .persistentSystemOverlays(chromeHidden ? .hidden : .automatic)
        .animation(.easeInOut(duration: 0.2), value: chromeHidden)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                bookmarkButton
                passageMenu
                settingsMenu
            }
        }
        .overlay(alignment: .bottomTrailing) {
            if showFocusButton && loadError == nil && rangeStart == nil { focusButton }
        }
        .overlay(alignment: .bottom) {
            if let start = rangeStart {
                HighlightBar(wordCount: segmentIndex.tokens(from: start, to: rangeEnd ?? start).count,
                             onColor: { makeHighlight($0, withNote: false) },
                             onNote: { makeHighlight(.yellow, withNote: true) },
                             onCancel: cancelRange)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: rangeStart == nil)
        .overlay(alignment: .top) {
            if copiedNote {
                Text("Citation copied")
                    .font(.footnote.weight(.medium))
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(.thinMaterial, in: Capsule())
                    .padding(.top, 8)
                    .transition(.opacity)
            }
        }
        .sheet(isPresented: $showLookup, onDismiss: {
            selection = nil
            openPendingEdit()
        }) {
            LookupSheet(selection: selection, work: selection?.work ?? work, library: library,
                        annotations: selection?.work == nil ? annotationsCoveringSelection : [],
                        onEditAnnotation: { a in
                            pendingEdit = a
                            showLookup = false
                        },
                        onStartHighlight: {
                            if let token = selection?.token { beginRange(token) }
                        },
                        canHighlight: selection?.work == nil)
                .presentationDetents([lookupDetent, .large])
                .presentationBackgroundInteraction(.enabled(upThrough: lookupDetent))
                .presentationDragIndicator(.hidden)    // LookupSheet draws its own: tap to close
        }
        .sheet(item: $editing) { a in
            NoteEditor(annotation: a, citation: citation(for: a),
                       onSave: { store.save($0) },
                       onDelete: { store.delete(a.id) })
        }
        .sheet(isPresented: $showAnnotations, onDismiss: openPendingEdit) {
            AnnotationsList(work: work,
                            order: readingOrder,
                            onSelect: { point in
                                showAnnotations = false
                                jump(to: point)
                            },
                            onEdit: { a in
                                pendingEdit = a
                                showAnnotations = false
                            })
        }
        .sheet(isPresented: $showCopticSigns) {
            CopticSignsView(work: work)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showGoTo) {
            GoToSheet(work: work, parts: parts) { target in
                showGoTo = false
                goTo(target)
            }
            .presentationDetents([.medium, .large])
        }
        .task(id: work.id) { load() }
        .task(id: ItemsKey(parts: parts.count, part: partIndex, metrics: metrics, layout: effectiveLayout,
                           parallel: activeCompanion == nil ? "" : parallelLanguage)) {
            rebuildItems()
        }
        .task(id: anchor) {
            // Save the place once reading settles, not on every line scrolled past.
            try? await Task.sleep(for: .milliseconds(600))
            if !Task.isCancelled { savePosition(anchor) }
        }
    }

    // MARK: Scrolling mode

    @State private var scrollID: String?
    @State private var chromeTracker = ChromeScrollTracker()

    private var scrollingReader: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(content.items) { item in
                    ReaderItemView(item: item, metrics: metrics, selection: selection,
                                   onTapToken: select, onTapBackground: backgroundTapped)
                }
                if partIndex + 1 < parts.count {
                    Button("Continue to \(parts[partIndex + 1].label)") { switchPart(partIndex + 1) }
                        .padding(.vertical, 24)
                        .frame(maxWidth: .infinity)
                }
                // Room to scroll the last lines above the lookup sheet; also a tap target.
                Color.clear.frame(height: 320)
                    .contentShape(Rectangle())
                    .onTapGesture(perform: backgroundTapped)
            }
            .scrollTargetLayout()
            .padding(.leading, metrics.leadingPadding)
            .padding(.trailing, metrics.trailingPadding)
            .padding(.top, 8)
            .background(GeometryReader { geometry in
                Color.clear.preference(key: ScrollOffsetKey.self,
                                       value: -geometry.frame(in: .named(Self.scrollSpace)).minY)
            })
        }
        .coordinateSpace(.named(Self.scrollSpace))
        .scrollPosition(id: $scrollID, anchor: .top)
        .onAppear {
            chromeTracker.pause()
            scrollID = anchor?.baseID
        }
        .onPreferenceChange(ScrollOffsetKey.self) { offset in
            // Hide the bars after reading on a little way; bring them back on
            // a deliberate scroll up, or at the top. Decided from distance
            // scrolled, not from which line is on top: hiding the bars moves
            // the content, and that must not count as scrolling.
            guard !showLookup, !focusMode else { return }
            if let hide = chromeTracker.update(offset: offset, hidden: chromeHidden) {
                chromeHidden = hide
            }
        }
        .onChange(of: scrollID) { _, new in
            guard let new, anchor?.baseID != new else { return }
            anchor = ReaderAnchor(baseID: new, location: 0)
        }
        .onChange(of: anchor) { _, newValue in
            // A jump requested from Go to…
            if let id = newValue?.baseID, id != scrollID {
                chromeTracker.pause()
                scrollID = id
            }
        }
    }

    private static let scrollSpace = "readerScroll"

    // MARK: Menus

    private var passageMenu: some View {
        Menu {
            Button("Go to…", systemImage: "arrow.right.to.line") { showGoTo = true }
            Button("Bookmarks & Notes", systemImage: "list.bullet.rectangle") { showAnnotations = true }
            if parts.count > 1 {
                Picker(work.partUnit, selection: Binding(get: { partIndex }, set: { switchPart($0) })) {
                    ForEach(parts) { Text($0.label).tag($0.id) }
                }
                .pickerStyle(.menu)
            }
            Divider()
            Button("Copy citation", systemImage: "doc.on.doc") { copyCitation() }
            if work.isCoptic {
                Button("Coptic signs", systemImage: "info.circle") { showCopticSigns = true }
            }
            if !work.isCoptic, let cite = currentCite {
                if let url = PerseusLinks.hopper(work: work, cite: cite) {
                    Button("Open in Perseus (Hopper)", systemImage: "safari") { openURL(url) }
                }
                if let url = PerseusLinks.scaife(work: work, cite: cite) {
                    Button("Open in Scaife Viewer", systemImage: "safari") { openURL(url) }
                }
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
    }

    private var numbersLabel: String {
        if work.isCoptic { return "Saying & page numbers" }
        if work.form == "history" { return "Chapter numbers" }
        if work.form == "sections" || work.form == "speeches" { return "Section numbers" }
        if work.form == "chapters" && work.kind == .prose && !work.isSanskrit { return "Section numbers" }   // Agricola, the Epitome
        if work.isBible || work.form == "chapters" { return "Verse numbers" }
        return work.kind == .verse ? "Line numbers" : "Stephanus numbers"
    }

    private var settingsMenu: some View {
        Menu {
            Toggle("Turn pages", isOn: $paged)
            Picker("Layout", selection: Binding(get: { effectiveLayout }, set: { layout = $0 })) {
                ForEach(layoutChoices) { Text($0.label).tag($0) }
            }
            if !companions.isEmpty {
                Picker("Parallel text", selection: $parallelLanguage) {
                    Text("None").tag("")
                    ForEach(companions.keys.sorted(), id: \.self) { Text($0).tag($0) }
                }
            }
            Toggle(numbersLabel, isOn: $showNumbers)
            Toggle("Hide-bars button", isOn: $showFocusButton)
            if work.isSanskrit {
                Toggle("Devanāgarī", isOn: $devanagari)
            }
            if work.isHebrew {
                Toggle("Cantillation marks", isOn: Binding(get: { !hideCantillation }, set: { hideCantillation = !$0 }))
            }
            if work.isHebrew || (work.isSanskrit && devanagari) {
                // Hebrew and Devanāgarī have their own sizes, kept separately from the other languages'
                if work.isHebrew {
                    Section("Hebrew text size") {
                        Button("Larger", systemImage: "textformat.size.larger") { hebrewFontSize = min(hebrewFontSize + 2, 44) }
                        Button("Smaller", systemImage: "textformat.size.smaller") { hebrewFontSize = max(hebrewFontSize - 2, 16) }
                    }
                } else {
                    Section("Devanāgarī text size") {
                        Button("Larger", systemImage: "textformat.size.larger") { devanagariFontSize = min(devanagariFontSize + 2, 44) }
                        Button("Smaller", systemImage: "textformat.size.smaller") { devanagariFontSize = max(devanagariFontSize - 2, 16) }
                    }
                }
                Section("Translation size") {
                    Button("Larger", systemImage: "textformat.size.larger") { fontSize = min(fontSize + 2, 36) }
                    Button("Smaller", systemImage: "textformat.size.smaller") { fontSize = max(fontSize - 2, 14) }
                }
            } else {
                Section("Text size") {
                    Button("Larger", systemImage: "textformat.size.larger") { fontSize = min(fontSize + 2, 36) }
                    Button("Smaller", systemImage: "textformat.size.smaller") { fontSize = max(fontSize - 2, 14) }
                }
            }
        } label: {
            Image(systemName: "textformat")
        }
    }

    // MARK: Position

    /// The citation at the top of the current page (or scroll position).
    private var currentCite: String? {
        guard let anchor else { return content.items.first?.cite }
        if anchor.baseID.hasPrefix("g"), let id = Int(anchor.baseID.dropFirst()), anchor.location == 0 {
            return content.segmentCites[id]
        }
        return content.items.first(where: { $0.baseID == anchor.baseID })?.cite
    }

    private func copyCitation() {
        guard let cite = currentCite else { return }
        UIPasteboard.general.string = PerseusLinks.citation(work: work, cite: cite)
        withAnimation { copiedNote = true }
        Task {
            try? await Task.sleep(for: .seconds(1.5))
            withAnimation { copiedNote = false }
        }
    }

    private func goTo(_ target: GoToSheet.Target) {
        switch target {
        case .part(let index):
            switchPart(index)
        case .segment(let partIndex, let segmentID):
            if partIndex != self.partIndex {
                pendingSegment = segmentID
                switchPart(partIndex)
            } else {
                anchor = content.segmentAnchors[segmentID]
            }
        }
    }

    @State private var pendingSegment: Int?

    private func switchPart(_ index: Int, atEnd: Bool = false) {
        guard parts.indices.contains(index), index != partIndex else { return }
        anchor = nil
        startAtEnd = atEnd
        partIndex = index
    }

    // Saved as "workID:partIndex:baseID:location;…" so each work reopens where you left it.
    private func savePosition(_ anchor: ReaderAnchor?) {
        guard let anchor else { return }
        var entries = savedPositions.split(separator: ";").map(String.init)
            .filter { !$0.hasPrefix("\(work.id):") }
        entries.append("\(work.id):\(partIndex):\(anchor.baseID):\(anchor.location)")
        savedPositions = entries.suffix(50).joined(separator: ";")
    }

    private func restorePosition() -> (part: Int, anchor: ReaderAnchor)? {
        for entry in savedPositions.split(separator: ";") {
            let f = entry.split(separator: ":").map(String.init)
            if f.count == 4, f[0] == String(work.id), let part = Int(f[1]), let loc = Int(f[3]) {
                return (part, ReaderAnchor(baseID: f[2], location: loc))
            }
        }
        return nil
    }

    // MARK: Interaction

    private func select(_ token: Token, in item: ReaderItem, tapY: CGFloat) {
        // Choosing words to highlight: a tap extends the selection to this word.
        if rangeStart != nil {
            rangeEnd = token
            return
        }
        selection = WordSelection(token: token, cite: content.segmentCites[token.segmentID] ?? item.cite,
                                  work: item.companionWork)
        showLookup = true
        // In scrolling mode, keep the tapped word above the lookup sheet.
        if !paged, tapY > 0.5 {
            chromeTracker.pause()
            withAnimation { scrollID = item.baseID }
        }
    }

    private func backgroundTapped() {
        if rangeStart != nil {
            cancelRange()
        } else if showLookup {
            showLookup = false
        } else if focusMode {
            setFocus(false)
        } else {
            chromeTracker.pause()
            chromeHidden.toggle()
        }
    }

    // MARK: Highlights and notes

    private var annotationContext: ReaderAnnotationContext {
        let chosen = rangeStart.map { ($0, rangeEnd ?? $0) }
        return ReaderAnnotationContext(marks: segmentIndex.marks(for: store.annotations(for: work.urn),
                                                                 selection: chosen),
                                       onLongPress: beginRange)
    }

    private var annotationsCoveringSelection: [Annotation] {
        guard let token = selection?.token else { return [] }
        return store.annotations(for: work.urn).filter { segmentIndex.covers($0, token) }
    }

    /// Long press on a word (or "Highlight" in the word card): start choosing words.
    private func beginRange(_ token: Token) {
        showLookup = false
        selection = nil
        rangeStart = token
        rangeEnd = nil
    }

    private func cancelRange() {
        rangeStart = nil
        rangeEnd = nil
    }

    private func makeHighlight(_ color: HighlightColor, withNote: Bool) {
        guard let start = rangeStart,
              let a = segmentIndex.annotation(from: start, to: rangeEnd ?? start, workURN: work.urn, color: color)
        else { return }
        store.save(a)
        cancelRange()
        if withNote { editing = a }
    }

    private func openPendingEdit() {
        if let a = pendingEdit {
            pendingEdit = nil
            editing = a
        }
    }

    private func readingOrder(_ point: TextPoint) -> Int {
        let position = segmentIndex.segmentID(for: point).flatMap { segmentIndex.order[$0] } ?? 1_000_000_000
        return position * 100_000 + point.offset
    }

    private func citation(for a: Annotation) -> String {
        let cite = a.start.cite == a.end.cite ? a.start.cite : "\(a.start.cite)–\(a.end.cite)"
        return PerseusLinks.citation(work: work, cite: cite)
    }

    private func jump(to point: TextPoint) {
        guard let id = segmentIndex.segmentID(for: point), let part = segmentIndex.part[id] else { return }
        goTo(.segment(part: part, segmentID: id))
    }

    // MARK: Bookmarks

    /// The segment at the top of the page (or screen).
    private var currentSegmentID: Int? {
        guard let anchor else { return part?.blocks.first?.segments.first?.id }
        guard let id = Int(anchor.baseID.dropFirst()) else { return nil }
        switch anchor.baseID.first {
        case "g", "h", "s": return id
        case "r", "e": return segmentIndex.firstOfBlock[id]
        default: return nil
        }
    }

    private var currentBookmark: Bookmark? {
        guard let id = currentSegmentID, let point = segmentIndex.point(segmentID: id, offset: 0) else { return nil }
        return store.bookmarks(for: work.urn).first {
            $0.point.cite == point.cite && $0.point.occurrence == point.occurrence
        }
    }

    private var bookmarkButton: some View {
        let marked = currentBookmark != nil
        return Button {
            toggleBookmark()
        } label: {
            Image(systemName: marked ? "bookmark.fill" : "bookmark")
        }
        .accessibilityLabel(marked ? "Remove bookmark" : "Bookmark this page")
    }

    private func toggleBookmark() {
        if let existing = currentBookmark {
            store.deleteBookmark(existing.id)
            return
        }
        guard let id = currentSegmentID, let point = segmentIndex.point(segmentID: id, offset: 0),
              let i = segmentIndex.order[id] else { return }
        let words = segmentIndex.ordered[i].text.split(separator: " ").prefix(8).joined(separator: " ")
        store.addBookmark(Bookmark(workURN: work.urn, point: point, snippet: words))
    }

    // MARK: No-bars reading

    /// A small, faint button in the corner that hides every bar (navigation
    /// bar, status bar, footer, home indicator) and brings them back.
    private var focusButton: some View {
        Button {
            setFocus(!focusMode)
        } label: {
            Image(systemName: focusMode ? "arrow.down.right.and.arrow.up.left"
                                        : "arrow.up.left.and.arrow.down.right")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Color(Palette.muted))
                .frame(width: 32, height: 32)
                .background(.ultraThinMaterial, in: Circle())
                .opacity(focusMode ? 0.35 : 0.7)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .padding(.trailing, 12)
        .padding(.bottom, 2)
        .accessibilityLabel(focusMode ? "Show bars" : "Hide bars")
    }

    private func setFocus(_ on: Bool) {
        chromeTracker.pause()
        focusMode = on
        chromeHidden = on
    }

    // MARK: Loading

    private func load() {
        guard let texts = library.texts else { return }
        do {
            let blocks = try texts.blocks(for: work)
            parts = Self.split(blocks, unit: work.partUnit)
            loadCompanion(texts)
            segmentIndex = SegmentIndex(parts: parts)
            if let saved = restorePosition(), parts.indices.contains(saved.part) {
                partIndex = saved.part
                anchor = saved.anchor
            }
        } catch {
            loadError = "\(error)"
        }
    }

    /// The parallel texts this work has (Vulgate ↔ LXX / Greek NT, Sahidic ↔
    /// Greek NT; the Greek NT has both Latin and Coptic): the counterpart
    /// works are loaded whole and each of this work's blocks is given its
    /// counterparts, per language.
    private func loadCompanion(_ texts: TextStore) {
        let map = texts.parallels(for: work)
        guard !map.isEmpty else { return }
        let ids = texts.workIDs(ofBlocks: Array(Set(map.values.flatMap { $0 })))
        var byID: [Int: Block] = [:]
        var workOf: [Int: Work] = [:]
        for id in ids {
            guard let other = library.works.first(where: { $0.id == id }),
                  let blocks = try? texts.blocks(for: other) else { continue }
            for b in blocks {
                byID[b.id] = b
                workOf[b.id] = other
            }
        }
        func language(_ w: Work) -> String {
            w.isLatin ? "Latin" : w.isCoptic ? "Coptic" : w.isOldEnglish ? "Old English"
                : w.isHebrew ? "Hebrew" : w.isSanskrit ? "Sanskrit" : "Greek"
        }
        var result: [String: Companion] = [:]
        for (block, others) in map {
            for id in others {
                guard let b = byID[id], let w = workOf[id] else { continue }
                result[language(w), default: Companion()].blocks[block, default: []].append(b)
                result[language(w), default: Companion()].workOf[id] = w
            }
        }
        companions = result
    }

    /// Long works are read a part at a time (keeps pagination quick): split at
    /// the first citation level, books of Homer or the Republic, pages of a
    /// Coptic codex.
    static func split(_ blocks: [Block], unit: String = "Book") -> [WorkPart] {
        func key(_ b: Block) -> String {
            guard let dot = b.citeStart.firstIndex(of: ".") else { return "" }
            return String(b.citeStart[..<dot])
        }
        // "Book 3", "Riddle 30b"; a named part ("Proem") as it is
        func label(_ k: String) -> String {
            k.isEmpty ? "" : k.first!.isNumber ? "\(unit) \(k)" : k
        }
        var parts: [WorkPart] = []
        var current: [Block] = []
        var currentKey: String?
        for block in blocks {
            let k = key(block)
            if let currentKey, k != currentKey {
                parts.append(WorkPart(id: parts.count, key: currentKey, label: label(currentKey), blocks: current))
                current = []
            }
            currentKey = k
            current.append(block)
        }
        if let currentKey {
            parts.append(WorkPart(id: parts.count, key: currentKey, label: label(currentKey), blocks: current))
        }
        return parts
    }

    private func rebuildItems() {
        guard let part else { return }
        content = ReaderItems.make(blocks: part.blocks, work: work, layout: effectiveLayout, metrics: metrics,
                                   companion: activeCompanion?.blocks ?? [:],
                                   companionWork: activeCompanion?.workOf ?? [:])
        if let segment = pendingSegment {
            anchor = content.segmentAnchors[segment]
            pendingSegment = nil
        } else if startAtEnd, let last = content.items.last {
            anchor = ReaderAnchor(baseID: last.baseID, location: 0)
            startAtEnd = false
        } else if let current = anchor {
            // e.g. English blocks hidden, or prose paragraphs joined, after a layout change
            anchor = content.resolve(current)
        }
        itemsVersion += 1
    }
}


// MARK: - Hiding the bars while scrolling

private struct ScrollOffsetKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// Decides when scrolling should hide or show the bars. It is a plain class,
/// not observed state, so measuring the offset on every frame doesn't
/// re-render the reader; only an actual change of the bars does.
///
/// The bars hide after `threshold` points of steady downward scrolling and
/// come back after the same distance upward, or near the top. After any
/// change of the bars (or a jump), offsets are ignored for a moment: showing
/// or hiding the navigation bar shifts the content, and that shift must not be
/// read as the reader scrolling, or the bars flicker forever.
final class ChromeScrollTracker {
    var threshold: CGFloat = 48
    var quietPeriod: TimeInterval = 0.45

    private var last: CGFloat?
    private var travel: CGFloat = 0
    private var quietUntil = Date.distantPast

    /// Ignore offsets for a moment (bars toggled by a tap, a programmatic scroll).
    func pause() {
        quietUntil = Date().addingTimeInterval(quietPeriod)
        travel = 0
    }

    /// `offset`: how far the content is scrolled from the top (grows going
    /// down). Returns the new hidden state, or nil to leave the bars alone.
    func update(offset: CGFloat, hidden: Bool) -> Bool? {
        defer { last = offset }
        guard let last, Date() >= quietUntil else { return nil }
        if offset < threshold {                  // at (or bouncing near) the top
            travel = 0
            return hidden ? change(to: false) : nil
        }
        let delta = offset - last
        guard abs(delta) > 0.5 else { return nil }
        if (delta > 0) != (travel > 0) { travel = 0 }   // direction changed
        travel += delta
        if travel > threshold, !hidden { return change(to: true) }
        if travel < -threshold, hidden { return change(to: false) }
        return nil
    }

    private func change(to hidden: Bool) -> Bool {
        pause()
        return hidden
    }
}
