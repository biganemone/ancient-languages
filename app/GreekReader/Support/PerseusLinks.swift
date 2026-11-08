import Foundation

/// Links into the Perseus Digital Library (patterns checked by hand, Nov 2026).
///
/// - Hopper (perseus.tufts.edu/hopper) accepts a version-less CTS URN with a
///   citation for every work: `text?doc=urn:cts:greekLit:tlg0012.tlg001:1.120`,
///   `…tlg0059.tlg001:5d` (Stephanus section), `…tlg0059.tlg030:1.327a`.
/// - Scaife (scaife.perseus.org) wants the edition URN. Plato is cited there by
///   Stephanus page only ("5", not "5d").
/// - Hopper's Word Study Tool takes a Unicode form: `morph?l=ἄειδε&la=greek`.
enum PerseusLinks {
    static func hopper(work: Work, cite: String) -> URL? {
        if work.isBible || work.isOldEnglish || work.isSanskrit { return nil }   // not at Perseus in this form (SBLGNT; Beowulf: unchecked)
        let (urn, ref) = split(work: work, cite: cite)
        var c = URLComponents(string: "https://www.perseus.tufts.edu/hopper/text")
        c?.queryItems = [URLQueryItem(name: "doc", value: "\(urn):\(ref)")]
        return c?.url
    }

    /// The Homeric Hymns are one work in the app but 33 texts at Perseus:
    /// "2.123" is line 123 of tlg0013.tlg002.
    private static func split(work: Work, cite: String) -> (urn: String, cite: String) {
        guard work.form == "hymns", let dot = cite.firstIndex(of: "."), let n = Int(cite[..<dot]) else {
            return (work.urn, cite)
        }
        return (work.urn + String(format: ".tlg%03d", n), String(cite[cite.index(after: dot)...]))
    }

    static func scaife(work: Work, cite: String) -> URL? {
        if work.isBible || work.isOldEnglish || work.isSanskrit { return nil }
        if work.form == "hymns" {
            let (urn, ref) = split(work: work, cite: cite)
            return URL(string: "https://scaife.perseus.org/reader/\(urn).perseus-grc2:\(ref)/")
        }
        var ref = cite
        if work.kind == .prose {
            // 1.327a -> 1.327, 5d -> 5
            ref = cite.replacingOccurrences(of: "[a-e]$", with: "", options: .regularExpression)
        }
        return URL(string: "https://scaife.perseus.org/reader/\(work.greekURN):\(ref)/")
    }

    static func wordStudy(form: String, latin: Bool = false) -> URL? {
        var c = URLComponents(string: "https://www.perseus.tufts.edu/hopper/morph")
        let bare = form.trimmingCharacters(in: CharacterSet(charactersIn: "\u{02BC}\u{2019}'"))
        c?.queryItems = [URLQueryItem(name: "l", value: bare), URLQueryItem(name: "la", value: latin ? "la" : "greek")]
        return c?.url
    }

    /// A conventional citation, e.g. "Homer, Iliad 1.120" or "Plato, Euthyphro 5d".
    static func citation(work: Work, cite: String) -> String {
        if work.form == "hymns" { return "Homeric Hymn \(cite)" }
        if work.isBible { return "\(work.title) \(cite.replacingOccurrences(of: ".", with: ":"))" }
        if work.author == work.title || work.isOldEnglish || work.isSanskrit { return "\(work.title) \(cite)" }
        return "\(work.author), \(work.title) \(cite)"
    }
}
