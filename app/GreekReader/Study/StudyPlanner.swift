import Foundation

/// A card to show: an entry in one direction.
struct StudyCard: Identifiable, Hashable {
    let entry: VocabEntry
    let direction: CardDirection
    var isNew: Bool
    var id: String { entry.cardKey(direction) }
}

/// Decides what a deck shows today.
///
/// - Due cards first, most overdue first. Learning cards (missed, due in a few
///   minutes) and reviews due any time today count as due.
/// - The day's maximum (100) includes the new cards (10): after a break, the
///   most overdue cards fill the day and no new words are introduced.
/// - New words come in the deck's order. With both directions, a word's
///   English → Greek card is introduced the day after its Greek → English card.
enum StudyPlanner {
    static func eligible(_ entries: [VocabEntry], deck: Deck, store: StudyStore) -> [VocabEntry] {
        entries.filter { e in
            e.gloss != nil && !store.isSetAside(e.key)
                && !(deck.skipFunctionWords && e.isFunctionWord && !deck.isMyWords)
        }
    }

    /// New-word order: by first appearance, by frequency, or a blend.
    static func ordered(_ entries: [VocabEntry], deck: Deck) -> [VocabEntry] {
        let byPosition = entries.sorted { $0.position < $1.position }
        switch deck.order {
        case .textOrder:
            return byPosition
        case .frequency:
            return entries.sorted { ($0.count, -$0.position) > ($1.count, -$1.position) }
        case .balanced:
            let n = Double(max(entries.count, 1))
            var posRank: [String: Double] = [:]
            for (i, e) in byPosition.enumerated() { posRank[e.key] = Double(i) / n }
            var freqRank: [String: Double] = [:]
            let byFrequency = entries.sorted { ($0.count, -$0.position) > ($1.count, -$1.position) }
            for (i, e) in byFrequency.enumerated() { freqRank[e.key] = Double(i) / n }
            let w = min(max(deck.balance, 0), 1)
            func score(_ e: VocabEntry) -> Double { w * (freqRank[e.key] ?? 1) + (1 - w) * (posRank[e.key] ?? 1) }
            return entries.sorted { (score($0), $0.position) < (score($1), $1.position) }
        }
    }

    struct Plan {
        var due: [StudyCard] = []
        var new: [StudyCard] = []
        var queue: [StudyCard] { due + new }
    }

    static func plan(deck: Deck, entries: [VocabEntry], store: StudyStore, now: Date = Date()) -> Plan {
        let words = eligible(entries, deck: deck, store: store)
        let directions: [CardDirection] = deck.bothDirections ? [.toEnglish, .fromEnglish] : [.toEnglish]
        let endOfDay = Calendar.current.startOfDay(for: now).addingTimeInterval(86_400)

        var due: [(StudyCard, Date)] = []
        for e in words {
            for d in directions {
                if let c = store.card(e.cardKey(d)), c.due < endOfDay {
                    due.append((StudyCard(entry: e, direction: d, isNew: false), c.due))
                }
            }
        }
        due.sort { $0.1 < $1.1 }

        let today = store.today(deck.id, now: now)
        let room = max(0, deck.maxPerDay - today.reviewed)
        var plan = Plan(due: Array(due.prefix(room).map(\.0)))
        var newRoom = min(max(0, deck.newPerDay - today.new), room - plan.due.count)
        guard newRoom > 0 else { return plan }

        let startOfDay = Calendar.current.startOfDay(for: now)
        for e in ordered(words, deck: deck) {
            for d in directions where store.card(e.cardKey(d)) == nil {
                if d == .fromEnglish {
                    // the sibling first, on an earlier day
                    guard let first = store.card(e.cardKey(.toEnglish)), first.introduced < startOfDay else { continue }
                }
                plan.new.append(StudyCard(entry: e, direction: d, isNew: true))
                newRoom -= 1
                if newRoom == 0 { return plan }
            }
        }
        return plan
    }
}
