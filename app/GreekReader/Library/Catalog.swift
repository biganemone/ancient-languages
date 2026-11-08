import Foundation

/// Every text the project offers, installed or not (Resources/Databases/catalog.json,
/// written by pipeline/make_catalog.py from the full build). The app ships some of
/// them (`bundled`, which can be removed and added back without a download); the
/// rest are modules downloaded from `downloads` (claude/loading-texts-plan.md).
struct Catalog {
    struct Entry: Codable, Identifiable, Hashable {
        let urn: String
        let language: String
        let author: String
        let title: String
        let translator: String
        let scope: String
        let words: Int              // tokens, to give an idea of size
        let bytes: Int?             // the module's download size
        var bundled: Bool? = nil    // ships in the app (texts.db.z)
        var module: String? = nil   // module file, under `downloads`
        var sha256: String? = nil
        var id: String { urn }
    }

    private struct File: Codable {
        let version: Int
        var build: String? = nil
        var downloads: String? = nil
        let works: [Entry]
    }

    let entries: [Entry]
    /// The build the bundled texts and the modules come from (pipeline/stamp_build.py).
    var build: String? = nil
    /// Where modules are downloaded from (empty until they're hosted).
    var downloads: String? = nil

    static func load() -> Catalog {
        guard let url = Bundle.main.url(forResource: "catalog", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(File.self, from: data) else {
            return Catalog(entries: [])
        }
        return Catalog(entries: file.works, build: file.build, downloads: file.downloads)
    }

    /// Entries not in the library, optionally for one language and/or author (group).
    func missing(from works: [Work], language: LibraryLanguage? = nil, author: String? = nil) -> [Entry] {
        let installed = Set(works.map(\.urn))
        return entries.filter { e in
            !installed.contains(e.urn)
                && (language == nil || LibraryLanguage(code: e.language) == language)
                && (author == nil || e.author == author)
        }
    }

    /// Whether an entry can be added now: it ships in the app, or downloads are hosted.
    func canAdd(_ e: Entry) -> Bool {
        e.bundled == true || (!(downloads ?? "").isEmpty && e.module != nil)
    }

    /// Languages the catalog offers that have nothing installed yet (for "Add languages").
    func languagesNotInstalled(works: [Work]) -> [LibraryLanguage] {
        let have = Set(works.compactMap { LibraryLanguage(code: $0.language) })
        let offered = Set(entries.compactMap { LibraryLanguage(code: $0.language) })
        return LibraryLanguage.allCases.filter { offered.contains($0) && !have.contains($0) }
    }
}
