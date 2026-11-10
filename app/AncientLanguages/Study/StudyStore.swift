import Foundation
import Observation
import StudyCore

/// Decks, every card's schedule, and the words set aside, kept as one JSON
/// file in Application Support (like notes and bookmarks). Cards are keyed by
/// word ("λέγω#gr"), never by database ids, so they survive rebuilds of the
/// texts.
@Observable
final class StudyStore {
    static let shared = StudyStore()

    private struct Saved: Codable {
        var decks: [Deck] = []
        var cards: [String: CardState] = [:]
        var known: Set<String> = []        // "I already know this": retired for good
        var hidden: Set<String> = []       // "Never show"
        var deleted: Set<String> = []      // deleted as wrong (e.g. a bad automatic lemma)
        var days: [String: DayCount] = [:] // "deck id|2026-11-06"
        var myWords: [ManualWord] = []
    }

    private var saved = Saved()
    private let url: URL?
    let fsrs = FSRS()

    var decks: [Deck] { saved.decks }
    var myWords: [ManualWord] { saved.myWords }

    init(directory: URL? = AnnotationStore.defaultDirectory) {
        url = directory?.appendingPathComponent("study.json")
        if let url, let data = try? Data(contentsOf: url) {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            saved = (try? decoder.decode(Saved.self, from: data)) ?? Saved()
        }
    }

    private func persist() {
        guard let url else { return }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(saved) {
            try? data.write(to: url, options: .atomic)
        }
    }

    // MARK: Decks

    func save(_ deck: Deck) {
        if let i = saved.decks.firstIndex(where: { $0.id == deck.id }) {
            saved.decks[i] = deck
        } else {
            saved.decks.append(deck)
        }
        persist()
    }

    func delete(deck id: UUID) {
        saved.decks.removeAll { $0.id == id }
        persist()
    }

    /// "My words", created the first time a word is added from the reader.
    var myWordsDeck: Deck {
        if let deck = saved.decks.first(where: \.isMyWords) { return deck }
        let deck = Deck(name: "My words", isMyWords: true)
        saved.decks.insert(deck, at: 0)
        persist()
        return deck
    }

    // MARK: Words set aside

    enum SetAside { case known, hidden, deleted }

    func isSetAside(_ entryKey: String) -> Bool {
        saved.known.contains(entryKey) || saved.hidden.contains(entryKey) || saved.deleted.contains(entryKey)
    }

    func setAside(_ entryKey: String, as kind: SetAside) {
        switch kind {
        case .known: saved.known.insert(entryKey)
        case .hidden: saved.hidden.insert(entryKey)
        case .deleted: saved.deleted.insert(entryKey)
        }
        for d in CardDirection.allCases { saved.cards[entryKey + "#" + d.rawValue] = nil }
        persist()
    }

    func restore(_ entryKey: String) {
        saved.known.remove(entryKey)
        saved.hidden.remove(entryKey)
        saved.deleted.remove(entryKey)
        persist()
    }

    var setAsideCount: Int { saved.known.count + saved.hidden.count + saved.deleted.count }

    // MARK: Cards

    func card(_ key: String) -> CardState? { saved.cards[key] }

    /// Record an answer. A new card is created on its first answer.
    func answer(_ cardKey: String, grade: FSRS.Grade, deck: UUID, isNew: Bool, exampleToken: Int?,
                now: Date = Date()) {
        var state = saved.cards[cardKey] ?? CardState(due: now, introduced: now, exampleToken: exampleToken)
        let elapsed = state.lastReview.map { now.timeIntervalSince($0) / 86_400 } ?? 0
        let firstToday = state.lastReview.map { !Calendar.current.isDate($0, inSameDayAs: now) } ?? true
        let memory = fsrs.review(state.memory, elapsedDays: elapsed, grade: grade)
        state.memory = memory
        state.due = fsrs.due(after: memory, grade: grade, now: now)
        state.lastReview = now
        state.reps += 1
        if grade == .again && !isNew { state.lapses += 1 }
        saved.cards[cardKey] = state
        // count each card once a day, on its first answer
        if firstToday || isNew {
            var day = saved.days[dayKey(deck, now)] ?? DayCount()
            day.reviewed += 1
            if isNew { day.new += 1 }
            saved.days[dayKey(deck, now)] = day
        }
        persist()
    }

    func today(_ deck: UUID, now: Date = Date()) -> DayCount {
        saved.days[dayKey(deck, now)] ?? DayCount()
    }

    private func dayKey(_ deck: UUID, _ date: Date) -> String {
        let c = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return String(format: "%@|%04d-%02d-%02d", deck.uuidString, c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    // MARK: My words

    func isInMyWords(_ key: String) -> Bool { saved.myWords.contains { $0.key == key } }

    func addToMyWords(key: String, tokenID: Int, workURN: String) {
        _ = myWordsDeck
        guard !isInMyWords(key) else { return }
        saved.myWords.append(ManualWord(key: key, tokenID: tokenID, workURN: workURN))
        restore(key)           // adding a word you had set aside brings it back
        persist()
    }

    func removeFromMyWords(_ key: String) {
        saved.myWords.removeAll { $0.key == key }
        persist()
    }
}
