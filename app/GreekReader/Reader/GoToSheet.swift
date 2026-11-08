import SwiftUI

/// "Go to" a line, a Stephanus section or a book.
///   Homer:     "1.350", "350" (in the current book is not assumed: 350 = book 1)
///   Sophocles: "350"
///   Plato:     "5d", "5" (first section of page 5), Republic "1.331c" or "331c"
struct GoToSheet: View {
    enum Target { case part(Int), segment(part: Int, segmentID: Int) }

    let work: Work
    let parts: [WorkPart]
    let onGo: (Target) -> Void

    @State private var text = ""
    @State private var notFound = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(placeholder, text: $text)
                        .keyboardType(.numbersAndPunctuation)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focused)
                        .onSubmit(go)
                    if notFound {
                        Text("No \(work.kind == .verse ? "line" : "section") \(text) in this text.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                } footer: {
                    Text(help)
                }
                if parts.count > 1 {
                    Section("Books") {
                        ForEach(parts) { part in
                            Button(part.label) { onGo(.part(part.id)) }
                        }
                    }
                }
            }
            .navigationTitle("Go to")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Go", action: go).disabled(text.isEmpty) }
            }
            .onAppear { focused = true }
        }
    }

    private var placeholder: String {
        if work.form == "sayings" { return "Saying, e.g. 77" }
        if work.isCodex { return "Page.line, e.g. 17.4, or a page" }
        if work.form == "hymns" { return "Hymn.line, e.g. 2.123, or a hymn" }
        if work.form == "history" { return "Book.chapter, e.g. 1.30, or 1.30.2" }
        if work.form == "sections" { return parts.count > 1 ? "Book.section, e.g. 1.30" : "Section, e.g. 12" }
        if work.form == "speeches" { return "Speech.section, e.g. 1.12" }
        if work.isBible { return "Chapter:verse, e.g. 5:3, or a chapter" }
        if work.form == "chapters" { return "Chapter.verse, e.g. 2.47, or a chapter" }
        if work.form == "letters" { return "Letter.section, e.g. 7.341c" }
        switch (work.kind, parts.count > 1) {
        case (.verse, true): return "Book.line, e.g. 6.237"
        case (.verse, false): return "Line, e.g. 450"
        case (.prose, true): return "Book.section, e.g. 1.331c"
        case (.prose, false): return "Stephanus section, e.g. 5d"
        }
    }

    private var help: String {
        if work.form == "sayings" { return "Sayings are numbered as in modern editions (Prologue = 0)." }
        if work.isCodex { return "Cited by the page and line of the codex, as in the critical editions." }
        if work.form == "history" { return "Cited by book, chapter and section." }
        if work.form == "sections" { return parts.count > 1 ? "Cited by book and section (Niese's numbers, as in the Loeb)." : "Cited by section." }
        if work.form == "speeches" { return "Cited by speech and section." }
        if work.isBible || work.form == "chapters" { return "Cited by chapter and verse." }
        return work.kind == .verse ? "Lines are numbered as in the Perseus edition."
                                   : "Stephanus numbers: a page and a section letter (a–e)."
    }

    private func go() {
        if let target = resolve(text.trimmingCharacters(in: .whitespaces)) {
            notFound = false
            onGo(target)
        } else {
            notFound = true
        }
    }

    private func resolve(_ query: String) -> Target? {
        guard !query.isEmpty else { return nil }
        var bookKey: String?
        var ref = query.lowercased()
        if work.isBible || work.form == "chapters" { ref = ref.replacingOccurrences(of: ":", with: ".") }
        if parts.count > 1, let dot = ref.firstIndex(of: ".") {
            bookKey = String(ref[..<dot])
            ref = String(ref[ref.index(after: dot)...])
        }
        // a codex page (or a hymn) on its own: its first line
        if work.isCodex || work.form == "hymns" || work.isBible || work.form == "chapters", bookKey == nil, let part = parts.first(where: { $0.key == ref }),
           let segment = part.blocks.first?.segments.first {
            return .segment(part: part.id, segmentID: segment.id)
        }
        let candidates = parts.filter { bookKey == nil || $0.key == bookKey }
        for part in candidates {
            for block in part.blocks {
                for segment in block.segments where matches(segment, ref) {
                    return .segment(part: part.id, segmentID: segment.id)
                }
            }
        }
        return nil
    }

    private func matches(_ segment: Segment, _ ref: String) -> Bool {
        // a work without books (De Amicitia "12", Agricola "12.3"): the citation itself, or its first section
        if segment.cite == ref || (parts.count == 1 && segment.cite.hasPrefix(ref + ".")) { return true }
        if work.form == "history" || work.form == "sections" {
            // cite "1.30.2" or "1.30"; ref (after the book) "30" or "30.2"
            let rest = segment.cite.split(separator: ".").dropFirst().map(String.init)
            guard let chapter = rest.first else { return false }
            return ref == chapter || ref == rest.joined(separator: ".")
        }
        let local = segment.cite.split(separator: ".").last.map(String.init)?.lowercased() ?? ""
        switch work.kind {
        case .verse:
            guard let wanted = Int(ref.filter(\.isNumber)), let n = segment.lineNumber else { return local == ref }
            return n >= wanted
        case .prose:
            if local == ref { return true }
            // a bare page number goes to its first section
            if Int(ref) != nil { return local.hasPrefix(ref) && local.dropFirst(ref.count).allSatisfy(\.isLetter) }
            return false
        }
    }
}
