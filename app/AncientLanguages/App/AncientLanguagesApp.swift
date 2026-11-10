import SwiftUI

@main
struct AncientLanguagesApp: App {
    @State private var library = Library()
    @State private var catalog = Catalog.load()
    @State private var modules: ModuleManager?

    init() {
        Fonts.registerBundledFonts()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if library.ready, let modules {
                    RootView(library: library, catalog: catalog)
                        .environment(modules)
                } else {
                    ProgressView("Preparing your library…")
                }
            }
            .environment(AnnotationStore.shared)
            .environment(StudyStore.shared)
            .task {
                guard !library.ready else { return }
                await library.prepare(catalog: catalog)
                modules = ModuleManager(catalog: catalog, library: library)
            }
        }
    }
}

/// Two tabs, Read and Study; the app opens on whichever was used last.
struct RootView: View {
    let library: Library
    let catalog: Catalog

    @AppStorage(SettingsKey.rootTab) private var tab = RootTab.read

    var body: some View {
        TabView(selection: $tab) {
            LibraryView(library: library, catalog: catalog)
                .tabItem { Label("Read", systemImage: "book") }
                .tag(RootTab.read)
            StudyTab(library: library)
                .tabItem { Label("Study", systemImage: "rectangle.stack") }
                .tag(RootTab.study)
        }
    }
}

/// The Study tab: the flashcard decks.
struct StudyTab: View {
    let library: Library

    var body: some View {
        NavigationStack {
            List {
                StudyHomeView(library: library)
            }
            .navigationTitle("Study")
            .navigationDestination(for: StudyRoute.self) { route in
                switch route {
                case .session(let id):
                    StudySessionView(deckID: id, library: library)
                        .toolbar(.hidden, for: .tabBar)
                }
            }
        }
    }
}

/// The reader's texts (library.db, which texts are added to and removed from)
/// and the lexicons, shared by every view: the bundled lexicon.db, plus any
/// downloaded dictionary files (Library/lexicon-<language>.db, Old Norse's).
@MainActor
@Observable
final class Library {
    private(set) var texts: TextStore?
    private(set) var lexicon: LexiconStore?
    /// Downloaded dictionaries, by language code. Lemma keys prefixed with
    /// that code ("non:…") are looked up there. A missing file isn't a
    /// `problem`: the lookup sheet offers to download it.
    private(set) var extraLexicons: [String: LexiconStore] = [:]
    private(set) var works: [Work] = []
    private(set) var problem: String?
    /// False while library.db is being made (first launch, or after an update).
    private(set) var ready = false

    /// Makes library.db if need be (off the main thread), then opens it.
    func prepare(catalog: Catalog) async {
        do {
            _ = try await Task.detached(priority: .userInitiated) {
                try LibraryDatabase.prepare(catalog: catalog)
            }.value
            reload()
            if problem != nil {
                // library.db won't open: make it again from the bundled texts
                _ = try await Task.detached(priority: .userInitiated) {
                    try LibraryDatabase.prepare(catalog: catalog, rebuild: true)
                }.value
                reload()
            }
        } catch {
            problem = "\(error)"
        }
        ready = true
    }

    /// Re-opens library.db after texts were added or removed.
    func reload() {
        guard let lexiconURL = Bundle.main.url(forResource: "lexicon", withExtension: "db") else {
            problem = "The lexicons aren't in the app bundle yet. Run pipeline/build.sh, then build again in Xcode."
            return
        }
        do {
            let texts = try TextStore(url: LibraryDatabase.url, mode: .readOnly)
            if lexicon == nil { lexicon = try LexiconStore(url: lexiconURL) }
            if extraLexicons.isEmpty { reloadDictionaries() }
            works = try texts.works()
            self.texts = texts
            problem = nil
            VocabularyCache.shared.reset()
        } catch {
            problem = "\(error)"
        }
    }

    /// (Re)opens the downloaded dictionary files: after one is installed,
    /// replaced or deleted (they're opened immutable, so a replaced file
    /// needs a new connection).
    func reloadDictionaries() {
        var stores: [String: LexiconStore] = [:]
        for code in LexiconFiles.installedLanguages() {
            if let store = try? LexiconStore(url: LexiconFiles.url(language: code)) { stores[code] = store }
        }
        extraLexicons = stores
    }

    /// Looks a lemma up in the lexicon that holds it: a downloaded
    /// dictionary for its language prefix ("non:"), otherwise lexicon.db.
    func lookup(lemmaKey: String, partOfSpeech: String? = nil) -> Lookup {
        if let colon = lemmaKey.firstIndex(of: ":"),
           let store = extraLexicons[String(lemmaKey[..<colon])] {
            return store.lookup(lemmaKey: lemmaKey, partOfSpeech: partOfSpeech)
        }
        return lexicon?.lookup(lemmaKey: lemmaKey, partOfSpeech: partOfSpeech) ?? Lookup()
    }

    /// Whether a downloaded dictionary for this language is open.
    func hasDictionary(language: String) -> Bool { extraLexicons[language] != nil }
}
