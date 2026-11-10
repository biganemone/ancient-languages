import SwiftUI
import UniformTypeIdentifiers

/// "Add Texts": every catalogued text not in the library, grouped by language
/// and author. A search field narrows the list by title, author or translator,
/// and a row of language capsules by language (opened from a language or an
/// author's group, it starts narrowed to that). Texts that ship with the app
/// are added at once; the others are downloaded. "Add from File…" takes a
/// module file (pipeline/make_modules.py) from Files.
struct AddTextsView: View {
    let catalog: Catalog
    let library: Library
    var language: LibraryLanguage? = nil
    var author: String? = nil

    @Environment(\.dismiss) private var dismiss
    @Environment(ModuleManager.self) private var modules
    @State private var unavailable: Catalog.Entry?
    @State private var importing = false
    @State private var query = ""
    /// The language shown; nil = all. Starts as the language the sheet was opened for.
    @State private var filter: LibraryLanguage?
    @State private var started = false

    /// Everything not yet in the library (for the author's group, if opened from one).
    private var missing: [Catalog.Entry] { catalog.missing(from: library.works, author: author) }

    /// Languages with something to add, in the usual order.
    private var languages: [LibraryLanguage] {
        let have = Set(missing.compactMap { LibraryLanguage(code: $0.language) })
        return LibraryLanguage.allCases.filter { have.contains($0) }
    }

    private var searching: Bool { !query.trimmingCharacters(in: .whitespaces).isEmpty }

    /// `missing`, narrowed by the language filter and the search.
    private var shown: [Catalog.Entry] {
        let q = query.trimmingCharacters(in: .whitespaces)
        return missing.filter { e in
            (filter == nil || LibraryLanguage(code: e.language) == filter)
                && (q.isEmpty || [e.title, e.author, e.translator, e.scope,
                                  LibraryLanguage(code: e.language)?.label ?? ""].contains { field in
                    field.range(of: q, options: [.caseInsensitive, .diacriticInsensitive]) != nil
                })
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if missing.isEmpty {
                    ContentUnavailableView {
                        Label("You have them all", systemImage: "checkmark.circle")
                    } description: {
                        Text(author.map { "Every text by or in \($0) is already in your library." }
                             ?? "Every available text is already in your library.")
                    }
                    .listRowBackground(Color.clear)
                } else {
                    if author == nil && languages.count > 1 {
                        languageFilter
                            .listRowBackground(Color.clear)
                            .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                    }
                    if shown.isEmpty {
                        if searching {
                            ContentUnavailableView.search(text: query)
                                .listRowBackground(Color.clear)
                        } else {
                            ContentUnavailableView {
                                Label("You have them all", systemImage: "checkmark.circle")
                            } description: {
                                Text("Every \(filter?.label ?? "") text is already in your library.")
                            }
                            .listRowBackground(Color.clear)
                        }
                    }
                    ForEach(groups, id: \.key) { group in
                        Section {
                            ForEach(group.entries) { entry in
                                Button { add([entry]) } label: { row(entry) }
                                    .buttonStyle(.plain)
                                    .disabled(modules.status[entry.urn] != nil && !failed(entry))
                            }
                        } header: {
                            HStack {
                                Text(group.key)
                                Spacer()
                                let addable = group.entries.filter { catalog.canAdd($0) && modules.status[$0.urn] == nil }
                                if addable.count > 1 {
                                    Button("Add All") { add(addable) }
                                        .font(.caption.weight(.semibold))
                                        .textCase(nil)
                                }
                            }
                        }
                    }
                }
            }
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: "Search titles, authors, translators")
            .navigationTitle(author ?? "Add Texts")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                if !started {
                    filter = language
                    started = true
                }
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Button("Add from File…", systemImage: "folder") { importing = true }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .accessibilityLabel("More")
                }
            }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.data], allowsMultipleSelection: true) { result in
                guard case .success(let urls) = result else { return }
                Task { for url in urls { await modules.addFromFile(url) } }
            }
            .alert(unavailable?.title ?? "", isPresented: Binding(get: { unavailable != nil },
                                                                   set: { if !$0 { unavailable = nil } })) {
                Button("OK", role: .cancel) { unavailable = nil }
            } message: {
                Text("This text doesn't come with the app, and downloading texts isn't available yet. It's coming in a later version.")
            }
            .alert("Couldn't add the text", isPresented: Binding(get: { modules.lastError != nil },
                                                                 set: { if !$0 { modules.clearError() } })) {
                Button("OK", role: .cancel) { modules.clearError() }
            } message: {
                Text(modules.lastError ?? "")
            }
        }
    }

    /// "All", then a capsule per language with texts to add (as on the Read tab), with counts.
    private var languageFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                capsule("All", count: missing.count, selected: filter == nil) { filter = nil }
                ForEach(languages) { lang in
                    capsule(lang.label,
                            count: missing.filter { LibraryLanguage(code: $0.language) == lang }.count,
                            selected: filter == lang) { filter = lang }
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func capsule(_ label: String, count: Int, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(label)
                Text("\(count)").monospacedDigit().foregroundStyle(selected ? Color.white.opacity(0.8) : Color.secondary)
            }
            .font(.subheadline.weight(selected ? .semibold : .regular))
            .padding(.horizontal, 14).padding(.vertical, 7)
            .background(Capsule().fill(selected ? Color.accentColor : Color(.secondarySystemFill)))
            .foregroundStyle(selected ? Color.white : Color.primary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func failed(_ e: Catalog.Entry) -> Bool {
        if case .failed = modules.status[e.urn] { return true }
        return false
    }

    private func add(_ entries: [Catalog.Entry]) {
        let ok = entries.filter { catalog.canAdd($0) }
        if ok.isEmpty, let first = entries.first {
            unavailable = first
            return
        }
        modules.add(ok)
    }

    private func row(_ e: Catalog.Entry) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(e.title).font(.headline)
                Text(details(e))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            switch modules.status[e.urn] {
            case .waiting?:
                Image(systemName: "clock").foregroundStyle(.secondary)
            case .downloading?, .installing?:
                ProgressView()
            case .failed?:
                Image(systemName: "exclamationmark.arrow.circlepath").foregroundStyle(.orange)
            case nil:
                Image(systemName: e.bundled == true ? "plus.circle" : "arrow.down.circle")
                    .foregroundStyle(catalog.canAdd(e) ? Color.accentColor : Color.secondary)
            }
        }
        .contentShape(Rectangle())
    }

    private func details(_ e: Catalog.Entry) -> String {
        var parts: [String] = []
        if e.scope != "complete" { parts.append(e.scope) }
        if !e.translator.isEmpty { parts.append("English: \(e.translator)") }
        parts.append("\(e.words.formatted()) words")
        if e.bundled == true {
            parts.append("comes with the app")
        } else if let bytes = e.bytes {
            parts.append(ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file))
        }
        switch modules.status[e.urn] {
        case .downloading?: parts.append("downloading…")
        case .installing?: parts.append("adding…")
        case .failed(let why)?: parts.append(why)
        default: break
        }
        return parts.joined(separator: " · ")
    }

    /// "Greek · Plato", in the catalog's order
    private var groups: [(key: String, entries: [Catalog.Entry])] {
        var order: [String] = []
        var by: [String: [Catalog.Entry]] = [:]
        for e in shown {
            let lang = LibraryLanguage(code: e.language)?.label ?? e.language
            let key = filter == nil && author == nil ? "\(lang) · \(e.author)" : e.author
            if by[key] == nil { order.append(key) }
            by[key, default: []].append(e)
        }
        return order.map { ($0, by[$0] ?? []) }
    }
}
