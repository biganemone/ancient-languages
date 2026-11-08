import Foundation

/// Word lists per deck, built once and kept until the deck's sources or
/// options change (building Homer's takes a moment).
@MainActor
final class VocabularyCache {
    static let shared = VocabularyCache()

    private var vocabulary: Vocabulary?
    private var built: [UUID: (signature: String, entries: [VocabEntry])] = [:]

    /// After texts are added or removed.
    func reset() {
        vocabulary = nil
        built = [:]
    }

    func vocabulary(_ library: Library) -> Vocabulary? {
        if vocabulary == nil, let texts = library.texts {
            vocabulary = Vocabulary(texts: texts, works: library.works)
        }
        return vocabulary
    }

    func entries(for deck: Deck, library: Library, store: StudyStore,
                 annotations: AnnotationStore) -> [VocabEntry] {
        // "My words" changes whenever a word is added or a highlight made
        let signature = deck.vocabularySignature
            + (deck.isMyWords ? "|\(store.myWords.count)|\(annotations.all.count)" : "")
        if let cached = built[deck.id], cached.signature == signature { return cached.entries }
        guard let vocabulary = vocabulary(library) else { return [] }
        let entries = vocabulary.entries(for: deck, myWords: store.myWords,
                                         highlights: deck.isMyWords ? annotations.all : [])
        built[deck.id] = (signature, entries)
        return entries
    }
}
