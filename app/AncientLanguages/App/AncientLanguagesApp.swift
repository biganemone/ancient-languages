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
/// and the bundled lexicons, shared by every view.
@MainActor
@Observable
final class Library {
    private(set) var texts: TextStore?
    private(set) var lexicon: LexiconStore?
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
            works = try texts.works()
            self.texts = texts
            problem = nil
            VocabularyCache.shared.reset()
        } catch {
            problem = "\(error)"
        }
    }
}
