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
                    Toggle("Also English → \(languageName)", isOn: $deck.bothDirections)
                    if !deck.isMyWords {
                        Toggle("Skip common function words", isOn: $deck.skipFunctionWords)
                    }
                    Toggle("Irregular verb forms as separate words", isOn: $deck.separateAorists)
                    if !deck.isMyWords {
                        Toggle("Every inflected form a card", isOn: $deck.allForms)
                    }
                } header: {
                    Text("Cards")
                } footer: {
                    Text(cardsHelp)
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

    /// The languages of the deck's texts (or, for My words, of the words added).
    private var languages: [LibraryLanguage] {
        let works = library.works
        var codes = Set<String>()
        if deck.isMyWords {
            let urns = Set(StudyStore.shared.myWords.map(\.workURN))
            codes = Set(works.filter { urns.contains($0.urn) }.map(\.language))
        } else {
            for s in deck.sources {
                if let author = s.author {
                    codes.formUnion(works.filter { $0.author == author && (s.language == nil || $0.language == s.language) }
                        .map(\.language))
                } else if let work = works.first(where: { $0.urn == s.workURN }) {
                    codes.insert(work.language)
                }
            }
        }
        let have = Set(codes.compactMap { LibraryLanguage(code: $0) })
        return LibraryLanguage.allCases.filter { have.contains($0) }
    }

    /// "Greek", "Greek and Latin"; before any texts are chosen, "the text".
    private var languageName: String {
        let names = languages.map(\.label)
        switch names.count {
        case 0: return "the text"
        case 1, 2: return names.joined(separator: " and ")
        default: return names.dropLast().joined(separator: ", ") + " and " + names.last!
        }
    }

    private var cardsHelp: String {
        let examples = languages.contains(.greek) ? " (in Greek, second aorists such as εἶπον, ἦλθον, ἔβην)" : ""
        return "Irregular verb forms\(examples) get cards of their own rather than counting under their verb. Every inflected form: for a first text, or a very hard one."
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
    @State private var language: LibraryLanguage?     // nil: every language
    @State private var query = ""

    private struct AuthorWorks: Identifiable {
        let author: String
        let language: LibraryLanguage?
        let code: String                // the works' language code, as stored
        let works: [Work]
        var id: String { "\(code)|\(author)" }
    }

    /// The languages with texts installed, in the usual order.
    private var languages: [LibraryLanguage] {
        let have = Set(library.works.compactMap { LibraryLanguage(code: $0.language) })
        return LibraryLanguage.allCases.filter { have.contains($0) }
    }

    private var searching: Bool { !query.trimmingCharacters(in: .whitespaces).isEmpty }

    /// Authors (or groups) and their works, in this language and matching the
    /// search: an author's name keeps all their works, otherwise the titles that match.
    private var authors: [AuthorWorks] {
        let q = query.trimmingCharacters(in: .whitespaces)
        func matches(_ s: String) -> Bool {
            !q.isEmpty && s.range(of: q, options: [.caseInsensitive, .diacriticInsensitive]) != nil
        }
        var order: [String] = []
        var groups: [String: [Work]] = [:]
        for w in library.works {
            if let language, LibraryLanguage(code: w.language) != language { continue }
            let key = "\(w.language)|\(w.author)"
            if groups[key] == nil { order.append(key) }
            groups[key, default: []].append(w)
        }
        return order.compactMap { key -> AuthorWorks? in
            var works = groups[key] ?? []
            guard let first = works.first else { return nil }
            if !q.isEmpty && !matches(first.author) {
                works = works.filter { matches($0.title) || matches($0.translator) }
                if works.isEmpty { return nil }
            }
            return AuthorWorks(author: first.author, language: LibraryLanguage(code: first.language),
                               code: first.language, works: works)
        }
    }

    /// Several languages on show: say which one each author is in.
    private func header(_ group: AuthorWorks) -> String {
        guard language == nil, languages.count > 1, let lang = group.language else { return group.author }
        return "\(group.author) · \(lang.label)"
    }

    private var languageFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip("All", selected: language == nil) { language = nil }
                ForEach(languages) { lang in
                    chip(lang.label, selected: language == lang) { language = lang }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 6)
        }
    }

    private func chip(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(selected ? .semibold : .regular))
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(Capsule().fill(selected ? Color.accentColor : Color(.secondarySystemFill)))
                .foregroundStyle(selected ? Color.white : Color.primary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    var body: some View {
        NavigationStack {
            List {
                if authors.isEmpty {
                    if searching {
                        ContentUnavailableView.search(text: query)
                    } else {
                        ContentUnavailableView("No texts", systemImage: "books.vertical")
                    }
                }
                ForEach(authors) { group in
                    let author = group.author
                    let works = group.works
                    let all = library.works.filter { $0.author == author && $0.language == group.code }
                    Section(header(group)) {
                        if all.count > 1 && works.count == all.count {
                            toggleRow("All of \(author)", DeckSource(author: author, language: group.code))
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
            .safeAreaInset(edge: .top, spacing: 0) {
                if languages.count > 1 {
                    languageFilter.background(.bar)
                }
            }
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: "Search titles and authors")
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
