import Foundation

/// IAST → Devanāgarī, for showing Sanskrit texts (stored in IAST) in
/// Devanāgarī. Returns the new text and, for every UTF-16 offset of the
/// source (and one past its end), the matching offset in the result, so
/// word ranges, taps and highlights keep working on the stored offsets.
///
/// With `joinSandhi`, a word ending in a consonant is joined to the next
/// word (the space dropped), as Devanāgarī is written: "tat karoti" →
/// तत्करोति, "karmaṇy eva" → कर्मण्येव. Words ending in a vowel, ṃ or ḥ keep
/// their space.
enum Devanagari {
    private static let vowels: [String: (independent: String, sign: String)] = [
        "a": ("अ", ""), "ā": ("आ", "ा"), "i": ("इ", "ि"), "ī": ("ई", "ी"), "u": ("उ", "ु"), "ū": ("ऊ", "ू"),
        "ṛ": ("ऋ", "ृ"), "ṝ": ("ॠ", "ॄ"), "ḷ": ("ऌ", "ॢ"), "ḹ": ("ॡ", "ॣ"), "e": ("ए", "े"), "ai": ("ऐ", "ै"),
        "o": ("ओ", "ो"), "au": ("औ", "ौ"),
    ]
    private static let consonants: [String: String] = [
        "k": "क", "kh": "ख", "g": "ग", "gh": "घ", "ṅ": "ङ", "c": "च", "ch": "छ", "j": "ज", "jh": "झ", "ñ": "ञ",
        "ṭ": "ट", "ṭh": "ठ", "ḍ": "ड", "ḍh": "ढ", "ṇ": "ण", "t": "त", "th": "थ", "d": "द", "dh": "ध", "n": "न",
        "p": "प", "ph": "फ", "b": "ब", "bh": "भ", "m": "म", "y": "य", "r": "र", "l": "ल", "ḻ": "ळ", "v": "व",
        "ś": "श", "ṣ": "ष", "s": "स", "h": "ह",
    ]
    private static let aspirable: Set<String> = ["k", "g", "c", "j", "ṭ", "ḍ", "t", "d", "p", "b"]
    private static let virama = "्"

    static func transliterate(_ text: String, joinSandhi: Bool = true) -> (text: String, map: [Int]) {
        let source = (text.precomposedStringWithCanonicalMapping as NSString)
        let n = source.length
        var units: [String] = []
        units.reserveCapacity(n)
        for i in 0..<n { units.append(source.substring(with: NSRange(location: i, length: 1)).lowercased()) }
        func unit(_ i: Int) -> String { i < n ? units[i] : "" }
        func isLetter(_ i: Int) -> Bool {
            let u = unit(i)
            return consonants[u] != nil || vowels[u] != nil || u == "ṃ" || u == "ḥ"
        }

        var out = ""
        var outLength = 0          // UTF-16 length of `out`
        var map = [Int](repeating: 0, count: n + 1)
        var pending = false        // a consonant waiting for its vowel
        func emit(_ s: String) {
            out += s
            outLength += (s as NSString).length
        }

        var i = 0
        while i < n {
            map[i] = outLength
            let u = units[i]
            // consonants (aspirates are two letters)
            if consonants[u] != nil {
                var key = u
                if aspirable.contains(u) && unit(i + 1) == "h" {
                    key = u + "h"
                }
                if u == "m" && unit(i + 1) == "\u{0310}" {          // m̐: candrabindu
                    if pending { emit(virama); pending = false }
                    emit("ँ")
                    map[i + 1] = outLength
                    i += 2
                    continue
                }
                if pending { emit(virama) }
                emit(consonants[key]!)
                pending = true
                if key.count == 2 { map[i + 1] = outLength }
                i += key.count
                continue
            }
            // vowels (ai and au are two letters)
            if vowels[u] != nil {
                var key = u
                if u == "a", unit(i + 1) == "i" || unit(i + 1) == "u" {
                    key = u + unit(i + 1)
                }
                let v = vowels[key]!
                emit(pending ? v.sign : v.independent)
                pending = false
                if key.count == 2 { map[i + 1] = outLength }
                i += key.count
                continue
            }
            switch u {
            case "ṃ": emit("ं")
            case "ḥ": emit("ः")
            case "'", "\u{2019}":
                if pending { emit(virama); pending = false }
                emit("ऽ")
            case " " where joinSandhi && (unit(i + 1) == "'" || unit(i + 1) == "\u{2019}"):
                // so 'ham: no space before the avagraha (सोऽहम्)
                if pending { emit(virama); pending = false }
                map[i] = outLength
                i += 1
                continue
            case " " where joinSandhi && pending && isLetter(i + 1):
                // join a consonant-final word to the next; a following consonant makes a conjunct
                if consonants[unit(i + 1)] != nil { emit(virama); pending = false }
                map[i] = outLength
                i += 1
                continue
            default:
                if pending { emit(virama); pending = false }
                map[i] = outLength
                emit(u == "|" ? "।" : units[i])
            }
            i += 1
        }
        if pending { emit(virama) }
        map[n] = outLength
        return (out, map)
    }
}
