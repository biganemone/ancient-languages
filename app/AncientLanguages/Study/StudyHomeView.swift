import SwiftUI

/// The Study shelf: decks with today's due and new counts.
struct StudyHomeView: View {
    let library: Library

    @Environment(StudyStore.self) private var store
    @Environment(AnnotationStore.self) private var annotations
    @State private var editing: Deck?

    var body: some View {
        Group {
            if store.decks.isEmpty {
                Section {
                    Text("Make a deck from any texts (a work, some of its books, or a whole author) and the app will introduce new words each day and bring back the ones you're forgetting. Words you add from the reader go to “My words”.")
                        .foregroundStyle(.secondary)
                    Button("New deck", systemImage: "plus") { editing = newDeck() }
                }
            } else {
                Section("Decks") {
                    ForEach(store.decks) { deck in
                        NavigationLink(value: StudyRoute.session(deck.id)) {
                            DeckRow(deck: deck, library: library)
                        }
                        .swipeActions {
                            Button("Delete", systemImage: "trash", role: .destructive) {
                                store.delete(deck: deck.id)
                            }
                            Button("Edit", systemImage: "slider.horizontal.3") { editing = deck }
                                .tint(.accentColor)
                        }
                        .contextMenu {
                            Button("Edit", systemImage: "slider.horizontal.3") { editing = deck }
                            Button("Delete deck", systemImage: "trash", role: .destructive) {
                                store.delete(deck: deck.id)
                            }
                        }
                    }
                    Button("New deck", systemImage: "plus") { editing = newDeck() }
                }
                Section {
                    Text("Your progress with a word is shared by every deck: a word you know from the Iliad isn't new in the Odyssey.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
        .sheet(item: $editing) { deck in
            DeckEditor(deck: deck, library: library) { store.save($0) }
        }
    }

    private func newDeck() -> Deck {
        Deck(name: "New deck")
    }
}

enum StudyRoute: Hashable {
    case session(UUID)
}

/// A deck in the list: its name, what it draws on, and today's counts.
struct DeckRow: View {
    let deck: Deck
    let library: Library

    @Environment(StudyStore.self) private var store
    @Environment(AnnotationStore.self) private var annotations

    var body: some View {
        let entries = VocabularyCache.shared.entries(for: deck, library: library, store: store,
                                                     annotations: annotations)
        let plan = StudyPlanner.plan(deck: deck, entries: entries, store: store)
        VStack(alignment: .leading, spacing: 3) {
            Text(deck.name).font(.headline)
            HStack(spacing: 10) {
                Label("\(plan.due.count) due", systemImage: "arrow.clockwise")
                Label("\(plan.new.count) new", systemImage: "sparkle")
                Text("\(StudyPlanner.eligible(entries, deck: deck, store: store).count) words")
                    .foregroundStyle(.tertiary)
            }
            .font(.caption).foregroundStyle(.secondary)
            .labelStyle(.titleAndIcon)
            if !deck.isMyWords {
                Text(DeckEditor.describe(deck.sources, works: library.works))
                    .font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
            }
        }
    }
}
