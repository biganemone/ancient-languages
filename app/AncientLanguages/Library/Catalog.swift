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

    /// A downloadable dictionary module (catalog.json `dictionaries`, optional:
    /// Old Norse's Zoëga and Cleasby–Vigfússon, in dict-non.db.z). Inflated, it
    /// is a lexicon file kept as Library/lexicon-<language>.db.
    struct Dictionary: Codable, Identifiable, Hashable {
        let language: String
        let id: String
        let title: String
        let module: String
        let bytes: Int?
        var sha256: String? = nil
    }

    private struct File: Codable {
        let version: Int
        var build: String? = nil
        var downloads: String? = nil
        let works: [Entry]
        var dictionaries: [Dictionary]? = nil
    }

    let entries: [Entry]
    /// Dictionary modules, one per file (entries sharing a module are listed once).
    var dictionaries: [Dictionary] = []
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
        var seen = Set<String>()
        let dictionaries = (file.dictionaries ?? []).filter { seen.insert($0.module).inserted }
        return Catalog(entries: file.works, dictionaries: dictionaries, build: file.build, downloads: file.downloads)
    }

    /// The dictionary module for a language, if it has one to download.
    func dictionary(for language: String) -> Dictionary? {
        dictionaries.first { $0.language == language }
    }

    /// Whether a dictionary can be downloaded now (downloads are hosted).
    func canDownload(_ d: Dictionary) -> Bool { !(downloads ?? "").isEmpty }

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
