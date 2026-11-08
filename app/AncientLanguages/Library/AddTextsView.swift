import SwiftUI
import UniformTypeIdentifiers

/// "Add Texts": every catalogued text not in the library, by language and
/// author, optionally narrowed to one language or one author's group. Texts
/// that ship with the app are added at once; the others are downloaded
/// (once downloads are hosted). "Add from File…" takes a module file
/// (pipeline/make_modules.py) from Files.
struct AddTextsView: View {
    let catalog: Catalog
    let library: Library
    var language: LibraryLanguage? = nil
    var author: String? = nil

    @Environment(\.dismiss) private var dismiss
    @Environment(ModuleManager.self) private var modules
    @State private var unavailable: Catalog.Entry?
    @State private var importing = false

    private var missing: [Catalog.Entry] { catalog.missing(from: library.works, language: language, author: author) }

    var body: some View {
        NavigationStack {
            List {
                if missing.isEmpty {
                    ContentUnavailableView {
                        Label("You have them all", systemImage: "checkmark.circle")
                    } description: {
                        Text(author.map { "Every text by or in \($0) is already in your library." }
                             ?? language.map { "Every \($0.label) text is already in your library." }
                             ?? "Every available text is already in your library.")
                    }
                    .listRowBackground(Color.clear)
                } else {
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
            .navigationTitle(author ?? language.map { "Add \($0.label) Texts" } ?? "Add Texts")
            .navigationBarTitleDisplayMode(.inline)
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
        for e in missing {
            let lang = LibraryLanguage(code: e.language)?.label ?? e.language
            let key = language == nil ? "\(lang) · \(e.author)" : e.author
            if by[key] == nil { order.append(key) }
            by[key, default: []].append(e)
        }
        return order.map { ($0, by[$0] ?? []) }
    }
}
