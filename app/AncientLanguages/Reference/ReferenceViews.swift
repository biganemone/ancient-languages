import SwiftUI

/// The Reference tab: the grammars, each with its contents and a search.
struct ReferenceTab: View {
    let library: Library

    var body: some View {
        NavigationStack {
            Group {
                if let store = library.grammar, !store.books.isEmpty {
                    List {
                        Section {
                            ForEach(store.books) { book in
                                NavigationLink(value: book) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(book.short).font(.headline)
                                        Text(book.title).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        } header: {
                            Text("Greek grammars")
                        } footer: {
                            Text("Tap “§” beside a word's parse in the reader to open the sections on its form and use.")
                        }
                    }
                    .navigationDestination(for: GrammarBook.self) { GrammarContentsView(store: store, book: $0) }
                    .navigationDestination(for: GrammarLocation.self) { GrammarSectionView(store: store, start: $0) }
                } else {
                    ContentUnavailableView("No reference works", systemImage: "books.vertical",
                                           description: Text("This build of the app has no grammars."))
                }
            }
            .navigationTitle("Reference")
        }
    }
}

/// A grammar's sections, under its parts and chapters; or, while searching,
/// the sections that match (a number goes straight to that section).
struct GrammarContentsView: View {
    let store: GrammarStore
    let book: GrammarBook

    @State private var all: [GrammarSection] = []
    @State private var query = ""

    private struct Chapter: Identifiable {
        let path: String
        let sections: [GrammarSection]
        var id: String { path + (sections.first?.n ?? "") }
    }

    /// Runs of sections with the same heading path, in book order.
    private var chapters: [Chapter] {
        var out: [Chapter] = []
        var current: [GrammarSection] = []
        for s in all {
            if let last = current.last, last.path != s.path {
                out.append(Chapter(path: last.path, sections: current))
                current = []
            }
            current.append(s)
        }
        if let last = current.last { out.append(Chapter(path: last.path, sections: current)) }
        return out
    }

    var body: some View {
        List {
            if query.trimmingCharacters(in: .whitespaces).isEmpty {
                ForEach(chapters) { chapter in
                    Section(chapter.path) {
                        ForEach(chapter.sections) { row($0) }
                    }
                }
                Section {
                    Text(book.credit).font(.footnote).foregroundStyle(.secondary)
                }
            } else {
                let results = store.search(book.id, query)
                if results.isEmpty {
                    ContentUnavailableView.search(text: query)
                }
                ForEach(results) { row($0, showPath: true) }
            }
        }
        .listStyle(.plain)
        .searchable(text: $query, prompt: "Section number or words")
        .navigationTitle(book.short)
        .navigationBarTitleDisplayMode(.inline)
        .task { if all.isEmpty { all = store.contents(book.id) } }
    }

    private func row(_ s: GrammarSection, showPath: Bool = false) -> some View {
        NavigationLink(value: s.location) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(s.label).font(.callout.monospacedDigit()).foregroundStyle(.secondary)
                    .frame(minWidth: 52, alignment: .leading)
                VStack(alignment: .leading, spacing: 1) {
                    Text(s.heading).font(.custom("GentiumBookPlus", size: 17)).lineLimit(2)
                    if showPath && !s.path.isEmpty {
                        Text(s.path).font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
                    }
                }
            }
        }
    }
}

/// One section, with the sections before and after it a tap away; cross-
/// references inside the text open where they point.
struct GrammarSectionView: View {
    let store: GrammarStore
    let start: GrammarLocation

    @State private var location: GrammarLocation?
    @State private var history: [GrammarLocation] = []

    private var here: GrammarLocation { location ?? start }

    var body: some View {
        let found = store.section(here)
        VStack(alignment: .leading, spacing: 4) {
            if let found {
                if !found.section.path.isEmpty {
                    Text(found.section.path).font(.caption).foregroundStyle(.secondary)
                }
                EntryWebView(html: "<div class=\"grammar\">\(found.html)</div>", anchor: here.anchor) { url in
                    // grammar://smyth/439
                    guard url.scheme == "grammar", let g = url.host(), let n = url.pathComponents.last else { return }
                    let target = GrammarLocation(grammar: g, n: n)
                    if store.section(target) != nil { go(target) }
                }
            } else {
                ContentUnavailableView("Section not found", systemImage: "questionmark.circle")
            }
        }
        .padding(.horizontal, 18)
        .background(Color(Palette.paper).ignoresSafeArea())
        .navigationTitle("\(store.book(here.grammar)?.short ?? "") \(found?.section.label ?? "§" + here.n)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let back = history.last {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(store.section(back)?.section.label ?? "§\(back.n)", systemImage: "arrow.uturn.backward") {
                        history.removeLast()
                        location = back
                    }
                    .labelStyle(.titleAndIcon)
                    .accessibilityLabel("Back to section \(back.n)")
                }
            }
            ToolbarItemGroup(placement: .bottomBar) {
                Button("Previous section", systemImage: "chevron.left") {
                    if let prev = store.neighbor(of: here, -1) { location = prev }
                }
                .disabled(store.neighbor(of: here, -1) == nil)
                Spacer()
                Button("Next section", systemImage: "chevron.right") {
                    if let next = store.neighbor(of: here, 1) { location = next }
                }
                .disabled(store.neighbor(of: here, 1) == nil)
            }
        }
    }

    /// Follow a cross-reference, remembering where we were.
    private func go(_ target: GrammarLocation) {
        history.append(here)
        location = target
    }
}

/// From the lookup card's "§": the sections on this word's form and use.
struct GrammarRefsSheet: View {
    let store: GrammarStore
    let parse: String
    let refs: [GrammarRef]
    var verbs: [GrammarVerb] = []

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if !verbs.isEmpty {
                    Section("Principal parts") {
                        ForEach(verbs) { verb in
                            NavigationLink(value: verb.location) {
                                HStack {
                                    Text(verb.headword).font(.custom("GentiumBookPlus", size: 18))
                                    Spacer()
                                    Text("\(verb.short), List of Verbs").font(.callout)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                if !refs.isEmpty {
                Section {
                    ForEach(refs) { ref in
                        NavigationLink(value: ref.location) {
                            HStack {
                                Text(ref.label)
                                Spacer()
                                Text("\(ref.short) §\(ref.n)").font(.callout.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                } header: {
                    Text(parse)
                }
                }
            }
            .navigationTitle("Grammar")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: GrammarLocation.self) { GrammarSectionView(store: store, start: $0) }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
