import SwiftUI

/// Create or change a deck: its texts, how new words are chosen, daily limits.
struct DeckEditor: View {
    @State var deck: Deck
    let library: Library
    let onSave: (Deck) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var choosingTexts = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Name") {
                    TextField("Name", text: $deck.name)
                }
                if deck.isMyWords {
                    Section {
                        Toggle("Include highlighted words", isOn: $deck.includeHighlights)
                    } footer: {
                        Text("Words you add from the reader (“Add to flashcards”) are always included.")
                    }
                } else {
                    Section("Texts") {
                        ForEach(deck.sources) { source in
                            Text(Self.describe([source], works: library.works))
                        }
                        .onDelete { deck.sources.remove(atOffsets: $0) }
                        Button("Add texts…", systemImage: "plus") { choosingTexts = true }
                    }
                    Section {
                        Picker("New words", selection: $deck.order) {
                            ForEach(NewWordOrder.allCases) { Text($0.label).tag($0) }
                        }
                        if deck.order == .balanced {
                            VStack(alignment: .leading) {
                                Slider(value: $deck.balance, in: 0...1)
                                HStack {
                                    Text("Text order")
                                    Spacer()
                                    Text("Most common")
                                }
                                .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    } footer: {
                        Text(orderHelp)
                    }
                }
                Section("Each day") {
                    Stepper("New words: \(deck.newPerDay)", value: $deck.newPerDay, in: 0...100)
                    Stepper("Most cards: \(deck.maxPerDay)", value: $deck.maxPerDay, in: 10...500, step: 10)
                }
                Section {
                    Toggle("Also English → Greek", isOn: $deck.bothDirections)
                    if !deck.isMyWords {
                        Toggle("Skip common function words", isOn: $deck.skipFunctionWords)
                    }
                    Toggle("Second aorists as separate words", isOn: $deck.separateAorists)
                    if !deck.isMyWords {
                        Toggle("Every inflected form a card", isOn: $deck.allForms)
                    }
                } header: {
                    Text("Cards")
                } footer: {
                    Text("Second aorists: εἶπον, ἦλθον, ἔβην get cards of their own. Every inflected form: for a first text, or a very hard one.")
                }
            }
            .navigationTitle(deck.isMyWords ? "My words" : "Deck")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(deck)
                        dismiss()
                    }
                    .disabled(!deck.isMyWords && deck.sources.isEmpty)
                }
            }
            .sheet(isPresented: $choosingTexts) {
                SourcePicker(library: library) { chosen in
                    deck.sources.append(contentsOf: chosen.filter { !deck.sources.contains($0) })
                    if deck.name == "New deck", let first = chosen.first {
                        deck.name = Self.describe([first], works: library.works)
                    }
                }
            }
        }
    }

    private var orderHelp: String {
        switch deck.order {
        case .textOrder: return "New words in the order you meet them reading."
        case .frequency: return "The commonest words in these texts first."
        case .balanced: return "Mostly the common words first, while still working from the beginning of the text to the end."
        }
    }

    /// "Homer (all)", "Iliad 1–6", "Apology"
    static func describe(_ sources: [DeckSource], works: [Work]) -> String {
        sources.map { s in
            if let author = s.author { return "\(author) (all)" }
            guard let work = works.first(where: { $0.urn == s.workURN }) else { return "?" }
            switch (s.fromPart, s.toPart) {
            case let (f?, t?) where f == t: return "\(work.title) \(f)"
            case let (f?, t?): return "\(work.title) \(f)–\(t)"
            case let (f?, nil): return "\(work.title) \(f)–end"
            case let (nil, t?): return "\(work.title) to \(t)"
            default: return work.title
            }
        }
        .joined(separator: ", ")
    }
}

/// Pick texts for a deck: whole authors, whole works, or a range of books.
struct SourcePicker: View {
    let library: Library
    let onDone: ([DeckSource]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var chosen: [DeckSource] = []
    @State private var rangeWork: Work?

    private struct AuthorWorks: Identifiable {
        let author: String
        let works: [Work]
        var id: String { author }
    }

    private var authors: [AuthorWorks] {
        var order: [String] = []
        var groups: [String: [Work]] = [:]
        for w in library.works {
            if groups[w.author] == nil { order.append(w.author) }
            groups[w.author, default: []].append(w)
        }
        return order.map { AuthorWorks(author: $0, works: groups[$0] ?? []) }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(authors) { group in
                    let author = group.author, works = group.works
                    Section(author) {
                        if works.count > 1 {
                            toggleRow("All of \(author)", DeckSource(author: author))
                        }
                        ForEach(works) { work in
                            HStack {
                                toggleRow(work.title, DeckSource(workURN: work.urn))
                                if partsCount(work) > 1 {
                                    Button("Books…") { rangeWork = work }
                                        .font(.caption).buttonStyle(.borderless)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Texts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        onDone(chosen)
                        dismiss()
                    }
                    .disabled(chosen.isEmpty)
                }
            }
            .sheet(item: $rangeWork) { work in
                RangePicker(work: work, parts: parts(work)) { source in chosen.append(source) }
                    .presentationDetents([.medium])
            }
        }
    }

    private func toggleRow(_ title: String, _ source: DeckSource) -> some View {
        let on = chosen.contains(source)
        return Button {
            if on { chosen.removeAll { $0 == source } } else { chosen.append(source) }
        } label: {
            HStack {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                Text(title).foregroundStyle(.primary)
                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
    }

    private func parts(_ work: Work) -> [String] {
        VocabularyCache.shared.vocabulary(library)?.parts(of: work).map(\.key) ?? []
    }

    private func partsCount(_ work: Work) -> Int { parts(work).count }
}

/// From book … to book … of one work.
struct RangePicker: View {
    let work: Work
    let parts: [String]
    let onDone: (DeckSource) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var from = 0
    @State private var to = 0

    var body: some View {
        NavigationStack {
            Form {
                Picker("From", selection: $from) {
                    ForEach(parts.indices, id: \.self) { Text("\(work.partUnit) \(parts[$0])").tag($0) }
                }
                Picker("To", selection: $to) {
                    ForEach(parts.indices, id: \.self) { Text("\(work.partUnit) \(parts[$0])").tag($0) }
                }
            }
            .navigationTitle(work.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        let (a, b) = (min(from, to), max(from, to))
                        onDone(DeckSource(workURN: work.urn, fromPart: parts[a], toPart: parts[b]))
                        dismiss()
                    }
                    .disabled(parts.isEmpty)
                }
            }
        }
    }
}
