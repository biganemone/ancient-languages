import Compression
import CryptoKit
import Foundation
import Observation

/// The reader's own database of texts (Application Support/Library/library.db).
///
/// The app ships its default texts compressed (texts.db.z, raw DEFLATE). On first
/// launch, and after an update that brings a new build, they are inflated into
/// library.db; texts are then added to it (from the bundle or a download) and
/// removed from it, bundled or not. Every module of one build keeps the full
/// build's row ids, which never collide between works, so adding a text is a
/// matter of copying its rows (claude/loading-texts-plan.md).
enum LibraryDatabase {
    static var directory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Library", isDirectory: true)
    }
    static var url: URL { directory.appendingPathComponent("library.db") }
    static var bundledURL: URL? { Bundle.main.url(forResource: "texts.db", withExtension: "z") }

    /// Bundled works the reader removed (re-applied after an update).
    static let removedKey = "libraryRemovedWorks"
    /// Works added by download (to be added again after an update with a new build).
    static let downloadedKey = "libraryDownloadedWorks"
    /// Works waiting to be downloaded again after an update.
    static let pendingKey = "libraryPendingWorks"

    enum Failure: Error, CustomStringConvertible {
        case missingBundle, wrongBuild(String, String), notHosted, checksum, noWorks, damaged(String), notDictionary
        var description: String {
            switch self {
            case .missingBundle:
                return "The texts aren't in the app bundle yet. Run pipeline/build.sh, then build again in Xcode."
            case .wrongBuild(let module, let library):
                return "This text was made for another version of the app (build \(module); this one is \(library))."
            case .notHosted: return "Downloading texts isn't available yet."
            case .checksum: return "The download was damaged. Please try again."
            case .noWorks: return "There was nothing new to add."
            case .damaged(let why): return "The texts unpacked from the app are damaged (\(why))."
            case .notDictionary: return "This file isn't a dictionary module."
            }
        }
    }

    /// Makes sure library.db exists and matches the bundled build; returns its build.
    /// `rebuild` starts again from the bundle even if library.db looks fine
    /// (after it failed to open).
    static func prepare(catalog: Catalog, rebuild: Bool = false) throws -> String? {
        let fm = FileManager.default
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        var current: String?
        if fm.fileExists(atPath: url.path), !rebuild {
            // A rollback journal, not WAL: a read-only connection to a WAL database
            // needs its -wal and -shm files, which it can't always make
            // ("unable to open database file", update 40).
            do {
                let db = try SQLiteDatabase(url: url, mode: .readWrite)
                try db.executeScript("PRAGMA journal_mode = DELETE")
                current = try db.string("SELECT value FROM meta WHERE key = 'build'")
            } catch {
                current = nil
            }
            if current != nil, current == catalog.build || catalog.build == nil {
                return current
            }
        }
        // first launch, or a new build: start again from the bundled texts
        guard let bundled = bundledURL else { throw Failure.missingBundle }
        let tmp = directory.appendingPathComponent("library.db.tmp")
        try? fm.removeItem(at: tmp)
        try inflate(bundled, to: tmp)
        do {    // closed before the move
            let db = try SQLiteDatabase(url: tmp, mode: .readWrite)
            try db.executeScript("PRAGMA journal_mode = DELETE")
            let check = try db.string("PRAGMA quick_check")
            if check != "ok" { throw Failure.damaged(check ?? "no result") }
            let removed = UserDefaults.standard.stringArray(forKey: removedKey) ?? []
            try removeWorks(urns: removed, in: db)
        }
        for suffix in ["", "-wal", "-shm", "-journal"] {
            try? fm.removeItem(at: URL(fileURLWithPath: url.path + suffix))
        }
        try fm.moveItem(at: tmp, to: url)
        var excluded = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true          // it can always be rebuilt
        try? excluded.setResourceValues(values)
        // texts downloaded for the previous build (or lost with a damaged library) have to be downloaded again
        if current != nil || rebuild {
            let downloaded = UserDefaults.standard.stringArray(forKey: downloadedKey) ?? []
            if !downloaded.isEmpty {
                UserDefaults.standard.set(downloaded, forKey: pendingKey)
                UserDefaults.standard.set([String](), forKey: downloadedKey)
            }
        }
        return catalog.build
    }

    /// Raw DEFLATE (pipeline/export_module.py deflate) → a file, streamed.
    static func inflate(_ source: URL, to destination: URL) throws {
        let input = try FileHandle(forReadingFrom: source)
        defer { try? input.close() }
        FileManager.default.createFile(atPath: destination.path, contents: nil)
        let output = try FileHandle(forWritingTo: destination)
        defer { try? output.close() }
        let filter = try InputFilter<Data>(.decompress, using: .zlib) { (length: Int) -> Data? in
            try input.read(upToCount: length)
        }
        while let page = try filter.readData(ofLength: 1 << 20), !page.isEmpty {
            try output.write(contentsOf: page)
        }
    }

    /// Copies the works of an inflated module (all of them, or those in `urns`)
    /// into library.db, skipping any already there. Returns the URNs added.
    static func copyWorks(from module: URL, urns: Set<String>?, build: String?) throws -> [String] {
        let db = try SQLiteDatabase(url: url, mode: .readWrite)
        try db.execute("ATTACH DATABASE ? AS m", [module.path])
        defer { try? db.execute("DETACH DATABASE m") }
        let moduleBuild = try? db.string("SELECT value FROM m.meta WHERE key = 'build'")
        if let build, let moduleBuild, moduleBuild != build {
            throw Failure.wrongBuild(moduleBuild, build)
        }
        var works: [(id: Int, urn: String, first: Int?, last: Int?)] = []
        try db.query("""
            SELECT id, urn, token_first, token_last FROM m.work
            WHERE urn NOT IN (SELECT urn FROM main.work)
            """) { r in
            works.append((r.int(0), r.string(1) ?? "", r.optionalInt(2), r.optionalInt(3)))
        }
        if let urns { works = works.filter { urns.contains($0.urn) } }
        guard !works.isEmpty else { return [] }
        try db.executeScript("BEGIN")
        do {
            for w in works {
                try db.execute("INSERT OR IGNORE INTO main.work SELECT * FROM m.work WHERE id = ?", [w.id])
                for table in ["part", "block", "segment"] {
                    try db.execute("INSERT OR IGNORE INTO main.\(table) SELECT * FROM m.\(table) WHERE work_id = ?", [w.id])
                }
                if let first = w.first, let last = w.last {
                    try db.execute("INSERT OR IGNORE INTO main.token SELECT * FROM m.token WHERE id BETWEEN ? AND ?",
                                   [first, last])
                    try db.execute("INSERT INTO main.morph SELECT * FROM m.morph WHERE token_id BETWEEN ? AND ?",
                                   [first, last])
                }
                try db.execute("INSERT OR IGNORE INTO main.parallel SELECT * FROM m.parallel WHERE urn = ? OR other_urn = ?",
                               [w.urn, w.urn])
            }
            // shared rows: words, tags, parses and Morpheus analyses
            for table in ["lemma", "tag", "parse", "analysis"] {
                try db.execute("INSERT OR IGNORE INTO main.\(table) SELECT * FROM m.\(table)")
            }
            try db.executeScript("COMMIT")
        } catch {
            try? db.executeScript("ROLLBACK")
            throw error
        }
        return works.map(\.urn)
    }

    /// Deletes works and everything that is theirs alone. Shared word, parse
    /// and analysis rows stay (a later text may need them).
    static func removeWorks(urns: [String], in db: SQLiteDatabase) throws {
        guard !urns.isEmpty else { return }
        try db.executeScript("BEGIN")
        do {
            for urn in urns {
                var rows: [(Int, Int?, Int?)] = []
                try db.query("SELECT id, token_first, token_last FROM work WHERE urn = ?", [urn]) { r in
                    rows.append((r.int(0), r.optionalInt(1), r.optionalInt(2)))
                }
                for (id, first, last) in rows {
                    if let first, let last {
                        try db.execute("DELETE FROM morph WHERE token_id BETWEEN ? AND ?", [first, last])
                        try db.execute("DELETE FROM token WHERE id BETWEEN ? AND ?", [first, last])
                    }
                    for table in ["segment", "block", "part"] {
                        try db.execute("DELETE FROM \(table) WHERE work_id = ?", [id])
                    }
                    try db.execute("DELETE FROM work WHERE id = ?", [id])
                }
                // Parallel links (by URN and citation) stay, both ways: a link whose other text
                // isn't installed finds no block, and they work again when the text comes back.
                // (The bundled texts carry only links among themselves: the Greek Iliad's links
                // to the Latin Homer come with the Latin, so they must outlive the Iliad's removal.)
            }
            try db.executeScript("COMMIT")
        } catch {
            try? db.executeScript("ROLLBACK")
            throw error
        }
        try? db.executeScript("PRAGMA incremental_vacuum")
    }

    /// Checks an inflated dictionary module and moves it into place as
    /// Library/lexicon-<language>.db (excluded from backup: it can be
    /// downloaded again). The file is kept as it is, not copied into library.db.
    static func installDictionary(from module: URL, language: String, build: String?) throws {
        do {    // closed before the move
            let db = try SQLiteDatabase(url: module, mode: .readOnly)
            guard (try? db.string("SELECT count(*) FROM resolve")) != nil,
                  (try? db.string("SELECT count(*) FROM entry")) != nil else { throw Failure.notDictionary }
            let moduleBuild = try? db.string("SELECT value FROM meta WHERE key = 'build'")
            if let build, let moduleBuild, moduleBuild != build {
                throw Failure.wrongBuild(moduleBuild, build)
            }
        }
        let fm = FileManager.default
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = LexiconFiles.url(language: language)
        try? fm.removeItem(at: destination)
        try fm.moveItem(at: module, to: destination)
        var excluded = destination
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? excluded.setResourceValues(values)
    }

    static func sha256(of file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 1 << 20), !chunk.isEmpty {
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

/// Adds and removes texts, and reports progress to the views.
@MainActor
@Observable
final class ModuleManager {
    enum Status: Equatable {
        case waiting, downloading, installing, failed(String)
    }

    private(set) var status: [String: Status] = [:]      // by URN
    /// Dictionary modules being downloaded, by language code.
    private(set) var dictionaryStatus: [String: Status] = [:]
    /// Downloaded dictionaries made for an earlier build, to download again.
    private(set) var staleDictionaries: [String] = []
    private(set) var lastError: String?
    let catalog: Catalog
    let library: Library

    init(catalog: Catalog, library: Library) {
        self.catalog = catalog
        self.library = library
        refreshStaleDictionaries()
    }

    var isBusy: Bool {
        status.values.contains { $0 != .waiting && !Self.isFailure($0) } || !queue.isEmpty
            || dictionaryStatus.values.contains { !Self.isFailure($0) }
    }
    private var queue: [Catalog.Entry] = []
    private var running = false

    private static func isFailure(_ s: Status) -> Bool { if case .failed = s { return true }; return false }

    /// Adds texts: bundled ones from the app, others by download.
    func add(_ entries: [Catalog.Entry]) {
        for e in entries where status[e.urn] == nil || Self.isFailure(status[e.urn]!) {
            status[e.urn] = .waiting
            queue.append(e)
        }
        // a language whose dictionaries download separately (Old Norse) gets them with its first text
        for language in Set(entries.map(\.language)) where needsDictionary(language) {
            installDictionary(language: language)
        }
        guard !running else { return }
        running = true
        Task { await drain() }
    }

    private func drain() async {
        while !queue.isEmpty {
            // bundled texts go together (one inflate of the bundle)
            let first = queue.removeFirst()
            var batch = [first]
            if first.bundled == true {
                batch += queue.filter { $0.bundled == true }
                queue.removeAll { $0.bundled == true }
            }
            do {
                let added = try await install(batch)
                for e in batch { status[e.urn] = nil }
                var downloaded = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.downloadedKey) ?? [])
                var removed = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.removedKey) ?? [])
                var pending = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.pendingKey) ?? [])
                for urn in added {
                    removed.remove(urn)
                    pending.remove(urn)
                    if first.bundled != true { downloaded.insert(urn) }
                }
                UserDefaults.standard.set(Array(downloaded), forKey: LibraryDatabase.downloadedKey)
                UserDefaults.standard.set(Array(removed), forKey: LibraryDatabase.removedKey)
                UserDefaults.standard.set(Array(pending), forKey: LibraryDatabase.pendingKey)
                library.reload()
            } catch {
                for e in batch { status[e.urn] = .failed("\(error)") }
                lastError = "\(error)"
            }
        }
        running = false
    }

    private func install(_ batch: [Catalog.Entry]) async throws -> [String] {
        let urns = Set(batch.map(\.urn))
        let build = catalog.build
        if batch.first?.bundled == true {
            for e in batch { status[e.urn] = .installing }
            guard let bundled = LibraryDatabase.bundledURL else { throw LibraryDatabase.Failure.missingBundle }
            return try await Task.detached(priority: .userInitiated) {
                let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("bundle-\(UUID().uuidString).db")
                defer { try? FileManager.default.removeItem(at: tmp) }
                try LibraryDatabase.inflate(bundled, to: tmp)
                return try LibraryDatabase.copyWorks(from: tmp, urns: urns, build: build)
            }.value
        }
        // one download per text
        var added: [String] = []
        for e in batch {
            guard let base = catalog.downloads, !base.isEmpty, let file = e.module,
                  let url = URL(string: base.hasSuffix("/") ? base + file : base + "/" + file) else {
                throw LibraryDatabase.Failure.notHosted
            }
            status[e.urn] = .downloading
            let (download, _) = try await URLSession.shared.download(from: url)
            status[e.urn] = .installing
            let sha = e.sha256
            added += try await Task.detached(priority: .userInitiated) {
                defer { try? FileManager.default.removeItem(at: download) }
                if let sha, try LibraryDatabase.sha256(of: download) != sha { throw LibraryDatabase.Failure.checksum }
                let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("module-\(UUID().uuidString).db")
                defer { try? FileManager.default.removeItem(at: tmp) }
                try LibraryDatabase.inflate(download, to: tmp)
                return try LibraryDatabase.copyWorks(from: tmp, urns: [e.urn], build: build)
            }.value
        }
        return added
    }

    /// Adds every text in a module file chosen in Files (.db.z or .db): for
    /// testing before downloads are hosted, and for sharing modules by hand.
    func addFromFile(_ url: URL) async {
        let build = catalog.build
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        // a dictionary module (dict-<language>.db.z) is kept as a file, not copied into library.db
        let name = url.lastPathComponent
        if name.hasPrefix("dict-") {
            let language = String(name.dropFirst("dict-".count).prefix { $0 != "." })
            do {
                try await Task.detached(priority: .userInitiated) {
                    let tmp = LibraryDatabase.directory.appendingPathComponent("dictionary-\(UUID().uuidString).db")
                    defer { try? FileManager.default.removeItem(at: tmp) }
                    if url.pathExtension == "z" {
                        try LibraryDatabase.inflate(url, to: tmp)
                    } else {
                        try FileManager.default.copyItem(at: url, to: tmp)
                    }
                    try LibraryDatabase.installDictionary(from: tmp, language: language, build: build)
                }.value
                library.reloadDictionaries()
                refreshStaleDictionaries()
            } catch {
                lastError = "\(error)"
            }
            return
        }
        do {
            let added = try await Task.detached(priority: .userInitiated) { () throws -> [String] in
                let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("file-\(UUID().uuidString).db")
                defer { try? FileManager.default.removeItem(at: tmp) }
                if url.pathExtension == "z" {
                    try LibraryDatabase.inflate(url, to: tmp)
                } else {
                    try FileManager.default.copyItem(at: url, to: tmp)
                }
                return try LibraryDatabase.copyWorks(from: tmp, urns: nil, build: build)
            }.value
            if added.isEmpty { throw LibraryDatabase.Failure.noWorks }
            let bundled = Set(catalog.entries.filter { $0.bundled == true }.map(\.urn))
            var downloaded = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.downloadedKey) ?? [])
            var removed = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.removedKey) ?? [])
            for urn in added {
                removed.remove(urn)
                if !bundled.contains(urn) { downloaded.insert(urn) }
            }
            UserDefaults.standard.set(Array(downloaded), forKey: LibraryDatabase.downloadedKey)
            UserDefaults.standard.set(Array(removed), forKey: LibraryDatabase.removedKey)
            library.reload()
        } catch {
            lastError = "\(error)"
        }
    }

    /// Removes texts, bundled or not. Highlights, notes, positions and flashcard
    /// progress are kept (they're keyed by URN and citation), for if they come back.
    func remove(urns: [String]) async {
        let bundled = Set(catalog.entries.filter { $0.bundled == true }.map(\.urn))
        let languages = Set(library.works.filter { urns.contains($0.urn) }.map(\.language))
        do {
            try await Task.detached(priority: .userInitiated) {
                let db = try SQLiteDatabase(url: LibraryDatabase.url, mode: .readWrite)
                try LibraryDatabase.removeWorks(urns: urns, in: db)
            }.value
            var removed = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.removedKey) ?? [])
            var downloaded = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.downloadedKey) ?? [])
            for urn in urns {
                if bundled.contains(urn) { removed.insert(urn) }
                downloaded.remove(urn)
            }
            UserDefaults.standard.set(Array(removed), forKey: LibraryDatabase.removedKey)
            UserDefaults.standard.set(Array(downloaded), forKey: LibraryDatabase.downloadedKey)
            library.reload()
            // the last text of a language with a downloaded dictionary: the dictionary goes too
            let left = Set(library.works.map(\.language))
            for language in languages.subtracting(left) where LexiconFiles.installedLanguages().contains(language) {
                removeDictionary(language: language)
            }
        } catch {
            lastError = "\(error)"
        }
    }

    func clearError() { lastError = nil }

    // MARK: Dictionary modules

    /// Whether a language has a dictionary module to download that isn't on disk (or under way).
    func needsDictionary(_ language: String) -> Bool {
        guard let d = catalog.dictionary(for: language), catalog.canDownload(d) else { return false }
        if let s = dictionaryStatus[language], !Self.isFailure(s) { return false }
        return !FileManager.default.fileExists(atPath: LexiconFiles.url(language: language).path)
    }

    /// Downloads a language's dictionary module (catalog.json `dictionaries`),
    /// checks its SHA-256 and build, and keeps it as Library/lexicon-<language>.db.
    func installDictionary(language: String) {
        if let s = dictionaryStatus[language], !Self.isFailure(s) { return }
        guard let d = catalog.dictionary(for: language) else { return }
        dictionaryStatus[language] = .waiting
        Task { await downloadDictionary(d) }
    }

    private func downloadDictionary(_ d: Catalog.Dictionary) async {
        let language = d.language
        let build = catalog.build
        do {
            guard let base = catalog.downloads, !base.isEmpty,
                  let url = URL(string: base.hasSuffix("/") ? base + d.module : base + "/" + d.module) else {
                throw LibraryDatabase.Failure.notHosted
            }
            dictionaryStatus[language] = .downloading
            let (download, _) = try await URLSession.shared.download(from: url)
            dictionaryStatus[language] = .installing
            let sha = d.sha256
            try await Task.detached(priority: .userInitiated) {
                defer { try? FileManager.default.removeItem(at: download) }
                if let sha, try LibraryDatabase.sha256(of: download) != sha { throw LibraryDatabase.Failure.checksum }
                // inflated beside its destination, so the move into place is a rename
                let tmp = LibraryDatabase.directory.appendingPathComponent("dictionary-\(UUID().uuidString).db")
                defer { try? FileManager.default.removeItem(at: tmp) }
                try LibraryDatabase.inflate(download, to: tmp)
                try LibraryDatabase.installDictionary(from: tmp, language: language, build: build)
            }.value
            dictionaryStatus[language] = nil
            library.reloadDictionaries()
            refreshStaleDictionaries()
        } catch {
            dictionaryStatus[language] = .failed("\(error)")
            let name = LibraryLanguage(code: language)?.label ?? language
            lastError = "The \(name) dictionaries couldn't be downloaded: \(error)"
        }
    }

    /// Deletes a language's downloaded dictionary file.
    func removeDictionary(language: String) {
        let url = LexiconFiles.url(language: language)
        for suffix in ["", "-journal", "-wal", "-shm"] {
            try? FileManager.default.removeItem(at: URL(fileURLWithPath: url.path + suffix))
        }
        dictionaryStatus[language] = nil
        library.reloadDictionaries()
        refreshStaleDictionaries()
    }

    /// Dictionaries on disk whose build isn't this catalog's (an update brought new
    /// editions): offered for download again with the texts.
    private func refreshStaleDictionaries() {
        guard let build = catalog.build else { staleDictionaries = []; return }
        staleDictionaries = LexiconFiles.installedLanguages().filter { language in
            catalog.dictionary(for: language) != nil
                && LexiconFiles.build(of: LexiconFiles.url(language: language)) != build
        }
    }

    /// Texts that were downloaded for an earlier build and need downloading again.
    var pending: [Catalog.Entry] {
        let urns = Set(UserDefaults.standard.stringArray(forKey: LibraryDatabase.pendingKey) ?? [])
        return catalog.entries.filter { urns.contains($0.urn) }
    }
}
