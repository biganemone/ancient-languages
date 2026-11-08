import SwiftUI

/// The bar shown while choosing words to highlight: a colour makes the
/// highlight, Note makes it and opens the note, Cancel drops the selection.
struct HighlightBar: View {
    let wordCount: Int
    let onColor: (HighlightColor) -> Void
    let onNote: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(spacing: 8) {
            Text(wordCount == 1 ? "Tap another word to extend the selection"
                                : "\(wordCount) words selected")
                .font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 14) {
                ForEach(HighlightColor.allCases) { color in
                    Button {
                        onColor(color)
                    } label: {
                        Circle().fill(Color(color.swatch))
                            .frame(width: 30, height: 30)
                            .overlay(Circle().stroke(Color.primary.opacity(0.15)))
                    }
                    .accessibilityLabel("Highlight \(color.name)")
                }
                Divider().frame(height: 26)
                Button("Note", systemImage: "square.and.pencil", action: onNote)
                    .labelStyle(.titleAndIcon)
                Button("Cancel", role: .cancel, action: onCancel)
            }
            .buttonStyle(.borderless)
        }
        .padding(.horizontal, 18).padding(.vertical, 12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.12), radius: 8, y: 2)
        .padding(.bottom, 12)
    }
}

/// Edit one highlight: its colour and its note, or delete it.
struct NoteEditor: View {
    @State var annotation: Annotation
    let citation: String
    let onSave: (Annotation) -> Void
    let onDelete: () -> Void

    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(annotation.quote)
                        .font(.custom(isCoptic ? "NotoSansCoptic-Regular" : "GentiumBookPlus", size: 19))
                        .lineLimit(6)
                    Text(citation).font(.caption).foregroundStyle(.secondary)
                }
                Section("Colour") {
                    HStack(spacing: 16) {
                        ForEach(HighlightColor.allCases) { color in
                            Button {
                                annotation.color = color
                            } label: {
                                Circle().fill(Color(color.swatch))
                                    .frame(width: 28, height: 28)
                                    .overlay(Circle().stroke(Color.primary, lineWidth: annotation.color == color ? 2 : 0))
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(color.name)
                        }
                    }
                }
                Section("Note") {
                    TextEditor(text: $annotation.note)
                        .frame(minHeight: 140)
                        .focused($focused)
                }
                Section {
                    if hasSavedNote {
                        Button("Delete note (keep highlight)", role: .destructive) {
                            annotation.note = ""
                            onSave(annotation)
                            dismiss()
                        }
                    }
                    Button(hasSavedNote ? "Delete highlight and note" : "Delete highlight", role: .destructive) {
                        onDelete()
                        dismiss()
                    }
                }
            }
            .onAppear { hasSavedNote = annotation.hasNote }
            .navigationTitle(annotation.hasNote ? "Note" : "Highlight")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(annotation)
                        dismiss()
                    }
                }
            }
        }
    }

    @State private var hasSavedNote = false

    private var isCoptic: Bool { annotation.quote.unicodeScalars.contains { (0x2C80...0x2CFF).contains($0.value) } }
}

/// A work's bookmarks and highlights (with their notes), in reading order.
/// Tap one to go there; swipe to delete (or, for a highlight, to edit).
struct AnnotationsList: View {
    let work: Work
    /// Position of a place in the work, for sorting.
    let order: (TextPoint) -> Int
    let onSelect: (TextPoint) -> Void
    let onEdit: (Annotation) -> Void

    @Environment(AnnotationStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var notesOnly = false
    @State private var confirming: Annotation?

    /// A visible delete button at the end of each row (swiping left also works).
    private func trashButton(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: "trash")
                .font(.body)
                .foregroundStyle(.red.opacity(0.8))
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(label)
    }

    private var bookmarks: [Bookmark] {
        store.bookmarks(for: work.urn).sorted { order($0.point) < order($1.point) }
    }

    private var highlights: [Annotation] {
        store.annotations(for: work.urn)
            .filter { !notesOnly || $0.hasNote }
            .sorted { order($0.start) < order($1.start) }
    }

    private var font: Font {
        .custom(work.isCoptic ? "NotoSansCoptic-Regular" : "GentiumBookPlus", size: 17)
    }

    var body: some View {
        NavigationStack {
            List {
                if bookmarks.isEmpty && store.annotations(for: work.urn).isEmpty {
                    Text("Nothing here yet. Tap the bookmark button to mark a page. Press and hold a word to start a highlight, then tap another word to extend it.")
                        .foregroundStyle(.secondary)
                }
                if !bookmarks.isEmpty && !notesOnly {
                    Section("Bookmarks") {
                        ForEach(bookmarks) { b in
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Button {
                                    onSelect(b.point)
                                } label: {
                                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                                        Image(systemName: "bookmark.fill").foregroundStyle(Color(Palette.speaker))
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(b.point.cite).font(.subheadline.monospacedDigit())
                                                .foregroundStyle(.primary)
                                            Text(b.snippet).font(font).lineLimit(1).foregroundStyle(.secondary)
                                        }
                                        Spacer(minLength: 0)
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.borderless)
                                trashButton("Delete bookmark") { store.deleteBookmark(b.id) }
                            }
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    store.deleteBookmark(b.id)
                                } label: { Label("Delete", systemImage: "trash") }
                            }
                        }
                    }
                }
                if !highlights.isEmpty {
                    Section(notesOnly ? "Notes" : "Highlights & Notes") {
                        ForEach(highlights) { a in
                            HStack(alignment: .top, spacing: 10) {
                                Button {
                                    onSelect(a.start)
                                } label: {
                                    HStack(alignment: .top, spacing: 10) {
                                        RoundedRectangle(cornerRadius: 2).fill(Color(a.color.swatch)).frame(width: 4)
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(a.quote).font(font).lineLimit(3).foregroundStyle(.primary)
                                            if a.hasNote {
                                                Text(a.note).font(.callout).foregroundStyle(.secondary).lineLimit(4)
                                            }
                                            Text(a.start.cite == a.end.cite ? a.start.cite
                                                                            : "\(a.start.cite)–\(a.end.cite)")
                                                .font(.caption.monospacedDigit()).foregroundStyle(.tertiary)
                                        }
                                        Spacer(minLength: 0)
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.borderless)
                                // a note asks first (keep the highlight, or delete both)
                                trashButton(a.hasNote ? "Delete note" : "Delete highlight") {
                                    if a.hasNote { confirming = a } else { store.delete(a.id) }
                                }
                            }
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    store.delete(a.id)
                                } label: { Label("Delete", systemImage: "trash") }
                                Button("Edit") { onEdit(a) }.tint(.accentColor)
                            }
                            .contextMenu {
                                Button("Edit", systemImage: "square.and.pencil") { onEdit(a) }
                                if a.hasNote {
                                    Button("Delete note (keep highlight)", systemImage: "text.badge.minus") {
                                        store.deleteNote(of: a.id)
                                    }
                                }
                                Button(a.hasNote ? "Delete highlight and note" : "Delete highlight",
                                       systemImage: "trash", role: .destructive) {
                                    store.delete(a.id)
                                }
                            }
                        }
                    }
                }
            }
            .confirmationDialog("Delete this note?",
                                isPresented: Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } }),
                                titleVisibility: .visible, presenting: confirming) { a in
                Button("Delete note, keep highlight", role: .destructive) { store.deleteNote(of: a.id) }
                Button("Delete highlight and note", role: .destructive) { store.delete(a.id) }
                Button("Cancel", role: .cancel) {}
            }
            .navigationTitle("Bookmarks & Notes")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Toggle("Notes only", isOn: $notesOnly).toggleStyle(.button)
                }
            }
        }
    }
}
