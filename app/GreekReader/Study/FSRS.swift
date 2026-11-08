import Foundation

/// FSRS-6, the Free Spaced Repetition Scheduler (open-spaced-repetition, MIT),
/// written from the published formulas
/// (github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm).
///
/// A card's memory is two numbers: stability S (days until recall falls to
/// 90%) and difficulty D (1…10). Each review updates them; the next review is
/// set for when recall is expected to have fallen to `retention`.
///
/// The app grades with two buttons, "Missed it" (Again, 1) and "Got it"
/// (Good, 3); Hard and Easy are supported for later.
/// pipeline/fsrs_check.py is a line-for-line Python twin used to check the numbers.
struct FSRS {
    enum Grade: Int, Codable { case again = 1, hard = 2, good = 3, easy = 4 }

    /// FSRS-6 default parameters (21 values).
    static let defaultWeights: [Double] = [
        0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796,
        1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542,
    ]

    var w: [Double] = FSRS.defaultWeights
    /// Probability of recall at which a card comes due.
    var retention: Double = 0.9
    var maximumInterval: Double = 36500
    /// After a miss, the card comes back this soon (relearning, same session).
    var relearnDelay: TimeInterval = 10 * 60

    struct Memory: Codable, Hashable {
        var stability: Double
        var difficulty: Double
    }

    // MARK: Formulas

    private var decay: Double { -w[20] }
    private var factor: Double { pow(0.9, 1 / decay) - 1 }

    /// Probability of recall after `days` with stability `s`.
    func retrievability(days: Double, stability s: Double) -> Double {
        pow(1 + factor * max(days, 0) / s, decay)
    }

    /// Days until recall falls to `retention`.
    func interval(stability s: Double) -> Double {
        let days = s / factor * (pow(retention, 1 / decay) - 1)
        return min(max(days.rounded(), 1), maximumInterval)
    }

    func initialStability(_ g: Grade) -> Double { max(w[g.rawValue - 1], 0.01) }

    func initialDifficulty(_ g: Grade) -> Double {
        clampD(w[4] - exp(w[5] * Double(g.rawValue - 1)) + 1)
    }

    private func clampD(_ d: Double) -> Double { min(max(d, 1), 10) }

    func nextDifficulty(_ d: Double, _ g: Grade) -> Double {
        let delta = -w[6] * Double(g.rawValue - 3)
        let damped = d + delta * (10 - d) / 9
        return clampD(w[7] * initialDifficulty(.easy) + (1 - w[7]) * damped)
    }

    func recallStability(d: Double, s: Double, r: Double, _ g: Grade) -> Double {
        let hard = g == .hard ? w[15] : 1
        let easy = g == .easy ? w[16] : 1
        return s * (exp(w[8]) * (11 - d) * pow(s, -w[9]) * (exp(w[10] * (1 - r)) - 1) * hard * easy + 1)
    }

    func forgetStability(d: Double, s: Double, r: Double) -> Double {
        let f = w[11] * pow(d, -w[12]) * (pow(s + 1, w[13]) - 1) * exp(w[14] * (1 - r))
        return min(f, s)
    }

    /// A second review on the same day (after a miss, say).
    func shortTermStability(s: Double, _ g: Grade) -> Double {
        var increase = exp(w[17] * (Double(g.rawValue) - 3 + w[18])) * pow(s, -w[19])
        if g.rawValue >= 2 { increase = max(increase, 1) }
        return s * increase
    }

    // MARK: Reviewing

    /// The memory after a review, given the memory before (nil for a new
    /// card) and the days since the last review.
    func review(_ memory: Memory?, elapsedDays: Double, grade g: Grade) -> Memory {
        guard let m = memory else {
            return Memory(stability: initialStability(g), difficulty: initialDifficulty(g))
        }
        let s: Double
        if elapsedDays < 1 {
            s = shortTermStability(s: m.stability, g)
        } else {
            let r = retrievability(days: elapsedDays, stability: m.stability)
            s = g == .again ? forgetStability(d: m.difficulty, s: m.stability, r: r)
                            : recallStability(d: m.difficulty, s: m.stability, r: r, g)
        }
        return Memory(stability: max(s, 0.01), difficulty: nextDifficulty(m.difficulty, g))
    }

    /// When the card should come back.
    func due(after memory: Memory, grade: Grade, now: Date) -> Date {
        if grade == .again { return now.addingTimeInterval(relearnDelay) }
        return now.addingTimeInterval(interval(stability: memory.stability) * 86_400)
    }
}
