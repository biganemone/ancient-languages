import SwiftUI
import StudyCore

/// A day's cards for one deck: tap to see the answer, then "Missed it" or
/// "Got it". A missed card comes back a few cards later.
struct StudySessionView: View {
    let deckID: UUID
    let library: Library

    @Environment(StudyStore.self) private var store
    @Environment(AnnotationStore.self) private var annotations
    @State private var queue: [StudyCard] = []
    @State private var started = false
    @State private var revealed = false
    @State private var answered = 0
    @State private var confirmDelete = false
    @State private var lexiconKey: LexiconKey?

    private var deck: Deck? { store.decks.first { $0.id == deckID } }

    var body: some View {
        VStack(spacing: 0) {
            if let card = queue.first {
                CardFace(card: card, revealed: revealed, library: library)
                    .contentShape(Rectangle())
                    .onTapGesture { withAnimation(.easeOut(duration: 0.15)) { revealed = true } }
                answerBar(card)
            } else if started {
                ContentUnavailableView {
                    Label("Done for today", systemImage: "checkmark.circle")
                } description: {
                    Text(answered > 0 ? "\(answered) cards. New words and reviews will be ready tomorrow."
                                      : "Nothing is due. New words and reviews will be ready tomorrow.")
                }
            }
        }
        .background(Color(Palette.paper).ignoresSafeArea())
        .navigationTitle(deck?.name ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let card = queue.first {
                ToolbarItem(placement: .principal) {
                    Text("\(queue.count) left").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
                }
                ToolbarItem(placement: .topBarTrailing) { cardMenu(card) }
            }
        }
        .confirmationDialog("Delete this card?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { setAside(.deleted) }
        } message: {
            Text("For a word the app got wrong. It won't be shown again in any deck.")
        }
        .sheet(item: $lexiconKey) { key in
            LexiconPeek(lemmaKey: key.key, coptic: key.coptic, library: library)
                .presentationDetents([.medium, .large])
        }
        .onAppear(perform: start)
    }

    private func start() {
        guard !started, let deck else { return }
        let entries = VocabularyCache.shared.entries(for: deck, library: library, store: store,
                                                     annotations: annotations)
        queue = StudyPlanner.plan(deck: deck, entries: entries, store: store).queue
        started = true
    }

    private func answerBar(_ card: StudyCard) -> some View {
        HStack(spacing: 12) {
            if revealed {
                Button { answer(.again) } label: {
                    Label("Missed it", systemImage: "xmark").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered).tint(.red)
                Button { answer(.good) } label: {
                    Label("Got it", systemImage: "checkmark").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(.green)
            } else {
                Button { withAnimation(.easeOut(duration: 0.15)) { revealed = true } } label: {
                    Text("Show answer").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
        }
        .controlSize(.large)
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    private func cardMenu(_ card: StudyCard) -> some View {
        Menu {
            Button("Open in lexicon", systemImage: "book") {
                lexiconKey = LexiconKey(key: card.entry.lookupKey, coptic: card.entry.coptic)
            }
            Divider()
            Button("I know this word", systemImage: "checkmark.seal") { setAside(.known) }
            Button("Never show", systemImage: "eye.slash") { setAside(.hidden) }
            Button("Delete card…", systemImage: "trash", role: .destructive) { confirmDelete = true }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
    }

    private func answer(_ grade: FSRS.Grade) {
        guard var card = queue.first, let deck else { return }
        store.answer(card.id, grade: grade, deck: deck.id, isNew: card.isNew,
                     exampleToken: card.entry.firstToken)
        queue.removeFirst()
        answered += 1
        if grade == .again {
            // back in a few cards (it is due again in 10 minutes)
            card.isNew = false
            queue.insert(card, at: min(4, queue.count))
        }
        revealed = false
    }

    private func setAside(_ kind: StudyStore.SetAside) {
        guard let card = queue.first else { return }
        store.setAside(card.entry.key, as: kind)
        queue.removeAll { $0.entry.key == card.entry.key }
        revealed = false
    }
}

struct LexiconKey: Identifiable {
    let key: String
    let coptic: Bool
    var id: String { key }
}

/// One side or both sides of a card.
struct CardFace: View {
    let card: StudyCard
    let revealed: Bool
    let library: Library

    private var font: String {
        card.entry.coptic ? "NotoSansCoptic-Regular"
            : card.entry.lookupKey.hasPrefix("heb:") ? "NotoSerifHebrew-Regular" : "GentiumBookPlus"
    }

    var body: some View {
        let e = card.entry
        ScrollView {
            VStack(spacing: 18) {
                Spacer(minLength: 40)
                if card.direction == .toEnglish || revealed {
                    Text(e.headword)
                        .font(.custom(font, size: 40))
                        .multilineTextAlignment(.center)
                    if let base = e.baseHeadword, revealed || card.direction == .toEnglish {
                        Text(e.kind == .aorist ? "aorist of \(base)" : "form of \(base)")
                            .font(.custom(font, size: 18)).foregroundStyle(.secondary)
                    }
                }
                if card.direction == .fromEnglish || revealed {
                    if card.direction == .toEnglish { Divider().padding(.horizontal, 40) }
                    Text(e.gloss ?? "")
                        .font(card.direction == .fromEnglish && !revealed ? .title2 : .title3)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                }
                if revealed, let example = VocabularyCache.shared.vocabulary(library)?.example(token: e.firstToken) {
                    ExampleLine(example: example, font: font)
                        .padding(.top, 8)
                }
                if !revealed {
                    Text("Tap to see the answer").font(.caption).foregroundStyle(.tertiary).padding(.top, 30)
                }
                Spacer(minLength: 20)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 16)
        }
    }
}

/// Where the deck first meets the word, with the word in bold.
struct ExampleLine: View {
    let example: Vocabulary.Example
    let font: String

    var body: some View {
        VStack(spacing: 6) {
            Text(attributed).font(.custom(font, size: 19)).multilineTextAlignment(.center)
            Text(example.citation).font(.caption).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 20)
    }

    private var attributed: AttributedString {
        var s = AttributedString(example.text)
        if let range = Range(example.wordRange, in: example.text),
           let lower = AttributedString.Index(range.lowerBound, within: s),
           let upper = AttributedString.Index(range.upperBound, within: s) {
            s[lower..<upper].inlinePresentationIntent = .stronglyEmphasized
            s[lower..<upper].foregroundColor = Color(Palette.speaker)
        }
        return s
    }
}

/// A word's entries in the lexica, opened from a card.
struct LexiconPeek: View {
    let lemmaKey: String
    let coptic: Bool
    let library: Library

    @State private var current: Lexicon = .lsj

    private var available: [Lexicon] {
        if coptic { return [.ccl, .crum] }
        if lemmaKey.hasPrefix("heb:") { return [.bdb, .strong] }
        if lemmaKey.hasPrefix("san:") { return [.md, .mw] }
        if lemmaKey.hasPrefix("ang:") { return [.klaeber, .bt] }
        if lemmaKey.first.map({ $0.isASCII && $0.isLetter }) == true { return [.ls, .lewis] }   // Latin
        return [.lsj, .ml, .aut, .abs]
    }

    var body: some View {
        let lookup = library.lookup(lemmaKey: lemmaKey)
        VStack(spacing: 10) {
            Picker("Lexicon", selection: $current) {
                ForEach(available) { Text($0.shortName).tag($0) }
            }
            .pickerStyle(.segmented)
            EntryWebView(html: (lookup.entries[current] ?? []).map { "<div class=\"entry\">\($0.html)</div>" }
                .joined(separator: "<hr>").nonEmpty ?? "<p class=\"none\">No entry in \(current.shortName).</p>")
        }
        .padding()
        .background(Color(Palette.paper).ignoresSafeArea())
        .onAppear {
            current = available.first { !(lookup.entries[$0] ?? []).isEmpty } ?? available[0]
        }
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
