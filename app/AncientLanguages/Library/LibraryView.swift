import SwiftUI

/// The Read tab: a row of language tabs, then the language's authors (or
/// groups, for anonymous and scriptural texts) with their works beneath.
struct LibraryView: View {
    let library: Library
    let catalog: Catalog

    @AppStorage(SettingsKey.libraryLanguage) private var language = LibraryLanguage.greek
    /// Groups whose lists are closed ("\n"-separated); all are open at first.
    @AppStorage(SettingsKey.collapsedAuthors) private var collapsedStore = ""
    @State private var query = ""
    @State private var adding: AddScope?
    @State private var removing: Removal?
    @Environment(ModuleManager.self) private var modules

    /// Texts about to be removed, waiting for confirmation.
    private struct Removal {
        let title: String
        let message: String
        let urns: [String]
    }

    /// What "Add Texts" was opened for.
    private struct AddScope: Identifiable {
        var language: LibraryLanguage?
        var author: String?
        var id: String { "\(language?.rawValue ?? "")|\(author ?? "")" }
    }

    private var searching: Bool { !query.trimmingCharacters(in: .whitespaces).isEmpty }
    private var collapsed: Set<String> { Set(collapsedStore.split(separator: "\n").map(String.init)) }

    var body: some View {
        NavigationStack {
            List {
                if let problem = library.problem {
                    Section {
                        Label(problem, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                }
                if !searching, !modules.pending.isEmpty {
                    Section {
                        let pending = modules.pending
                        Button {
                            modules.add(pending)
                        } label: {
                            Label("Download \(pending.count == 1 ? "1 text" : "\(pending.count) texts") again",
                                  systemImage: "arrow.down.circle")
                        }
                        .disabled(pending.allSatisfy { modules.status[$0.urn] != nil })
                    } footer: {
                        Text("This version of the app has new editions of the texts, so texts you downloaded need downloading again.")
                    }
                }
                if !searching {
                    languageTabs
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                }
                if searching && groups.isEmpty {
                    ContentUnavailableView.search(text: query)
                        .listRowBackground(Color.clear)
                }
                ForEach(groups) { group in
                    let open = searching || !collapsed.contains(group.key)
                    Section {
                        if open {
                            ForEach(group.works) { workRow($0) }
                            if !searching, !catalog.missing(from: library.works, language: shownLanguage,
                                                            author: group.author).isEmpty {
                                Button {
                                    adding = AddScope(language: shownLanguage, author: group.author)
                                } label: {
                                    Label("Add Text", systemImage: "plus.circle")
                                }
                            }
                        }
                    } header: {
                        groupHeader(group, open: open)
                    }
                }
                if !searching {
                    Section {
                        Text(credits(shownLanguage))
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .searchable(text: $query, prompt: "Search titles and authors")
            .navigationTitle("Read")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        adding = AddScope(language: nil, author: nil)
                    } label: {
                        Label("Add Texts", systemImage: "plus")
                            .labelStyle(.titleAndIcon)
                    }
                }
            }
            .sheet(item: $adding) { scope in
                AddTextsView(catalog: catalog, library: library, language: scope.language, author: scope.author)
            }
            .confirmationDialog(removing?.title ?? "", isPresented: Binding(get: { removing != nil },
                                                                            set: { if !$0 { removing = nil } }),
                                titleVisibility: .visible, presenting: removing) { removal in
                Button("Remove", role: .destructive) {
                    Task { await modules.remove(urns: removal.urns) }
                }
            } message: { removal in
                Text(removal.message)
            }
            .navigationDestination(for: Work.self) { work in
                ReaderView(work: work, library: library)
                    .toolbar(.hidden, for: .tabBar)     // the page gets the whole screen
            }
        }
    }

    // MARK: Languages

    /// The languages with texts installed, in the usual order.
    private var languages: [LibraryLanguage] {
        let have = Set(library.works.compactMap { LibraryLanguage(code: $0.language) })
        return LibraryLanguage.allCases.filter { have.contains($0) }
    }

    private var shownLanguage: LibraryLanguage {
        languages.contains(language) ? language : (languages.first ?? .greek)
    }

    /// A tab per language, scrolling sideways once there are many; "+" when the
    /// catalog offers a language with nothing installed.
    private var languageTabs: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(languages) { lang in
                        let selected = lang == shownLanguage
                        Button {
                            language = lang
                            withAnimation { proxy.scrollTo(lang.id, anchor: .center) }
                        } label: {
                            Text(lang.label)
                                .font(.subheadline.weight(selected ? .semibold : .regular))
                                .padding(.horizontal, 14).padding(.vertical, 7)
                                .background(Capsule().fill(selected ? Color.accentColor : Color(.secondarySystemFill)))
                                .foregroundStyle(selected ? Color.white : Color.primary)
                        }
                        .buttonStyle(.plain)
                        .id(lang.id)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .contextMenu {
                            Button(role: .destructive) {
                                confirmRemoval(library.works.filter { LibraryLanguage(code: $0.language) == lang },
                                               name: "all \(lang.label) texts")
                            } label: {
                                Label("Remove \(lang.label)…", systemImage: "trash")
                            }
                        }
                    }
                    if !catalog.languagesNotInstalled(works: library.works).isEmpty {
                        Button {
                            adding = AddScope(language: nil, author: nil)
                        } label: {
                            Image(systemName: "plus")
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(Capsule().strokeBorder(Color.secondary.opacity(0.4)))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Add languages")
                    }
                }
                .padding(.horizontal, 16)
            }
            .onAppear { proxy.scrollTo(shownLanguage.id, anchor: .center) }
        }
    }

    // MARK: Groups

    private struct AuthorGroup: Identifiable {
        let author: String           // the author, or the group (Torah, New Testament, Upaniṣads…)
        let language: LibraryLanguage?
        let works: [Work]
        var key: String { "\(language?.rawValue ?? "")|\(author)" }
        var id: String { key }
    }

    private var groups: [AuthorGroup] {
        let q = query.trimmingCharacters(in: .whitespaces)
        // A search looks through every language; otherwise, this language's works.
        let works: [Work]
        if q.isEmpty {
            works = library.works.filter { LibraryLanguage(code: $0.language) == shownLanguage }
        } else {
            works = library.works.filter { work in
                [work.title, work.author, work.translator].contains { field in
                    field.range(of: q, options: [.caseInsensitive, .diacriticInsensitive]) != nil
                }
            }
        }
        var order: [String] = []
        var by: [String: [Work]] = [:]
        var langOf: [String: LibraryLanguage?] = [:]
        for work in works {
            let lang = LibraryLanguage(code: work.language)
            let key = "\(lang?.rawValue ?? "")|\(work.author)"
            if by[key] == nil {
                order.append(key)
                langOf[key] = lang
            }
            by[key, default: []].append(work)
        }
        return order.map { key in
            let works = by[key] ?? []
            return AuthorGroup(author: works.first?.author ?? "", language: langOf[key] ?? nil, works: works)
        }
    }

    /// Tap to close or open a group's list.
    private func groupHeader(_ group: AuthorGroup, open: Bool) -> some View {
        Button {
            guard !searching else { return }
            var set = collapsed
            if open { set.insert(group.key) } else { set.remove(group.key) }
            withAnimation(.easeInOut(duration: 0.2)) {
                collapsedStore = set.sorted().joined(separator: "\n")
            }
        } label: {
            HStack {
                Text(searching && group.language != nil ? "\(group.author) · \(group.language!.label)" : group.author)
                Spacer()
                Text("\(group.works.count)").monospacedDigit()
                Image(systemName: "chevron.right")
                    .rotationEffect(.degrees(open ? 90 : 0))
                    .font(.caption.weight(.semibold))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint(open ? "Hides the works" : "Shows the works")
        .contextMenu {
            Button(role: .destructive) {
                confirmRemoval(group.works, name: group.works.count == 1 ? group.works[0].title : "all of \(group.author)")
            } label: {
                Label(group.works.count == 1 ? "Remove Text…" : "Remove All…", systemImage: "trash")
            }
        }
    }

    private func workRow(_ work: Work) -> some View {
        NavigationLink(value: work) {
            VStack(alignment: .leading, spacing: 2) {
                Text(work.title).font(.headline)
                Text(subtitle(work))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                confirmRemoval([work], name: work.title)
            } label: {
                Label("Remove", systemImage: "trash")
            }
        }
        .contextMenu {
            Button(role: .destructive) {
                confirmRemoval([work], name: work.title)
            } label: {
                Label("Remove from Library…", systemImage: "trash")
            }
        }
    }

    /// Asks before removing; says whether the texts can come back without a download.
    private func confirmRemoval(_ works: [Work], name: String) {
        guard !works.isEmpty else { return }
        let bundled = Set(catalog.entries.filter { $0.bundled == true }.map(\.urn))
        let all = works.allSatisfy { bundled.contains($0.urn) }
        let none = works.allSatisfy { !bundled.contains($0.urn) }
        let back = all ? "You can add \(works.count == 1 ? "it" : "them") back at any time from Add Texts."
            : none ? "To add \(works.count == 1 ? "it" : "them") back you'll need to download \(works.count == 1 ? "it" : "them") again."
            : "You can add them back from Add Texts (some will need downloading again)."
        removing = Removal(title: "Remove \(name)?",
                           message: "Your highlights, notes and flashcards are kept. " + back,
                           urns: works.map(\.urn))
    }

    private func subtitle(_ work: Work) -> String {
        if work.isCoptic {
            if work.isBible { return "Sahidic Bible 2 · English: \(work.translator)" }
            return work.parseSource == "scriptorium" ? "Coptic SCRIPTORIUM edition"
                                                     : "Text from Marcion · automatic analysis"
        }
        if work.isOldEnglish && work.translator.isEmpty {
            return "Text of the Anglo-Saxon Poetic Records · automatic analysis"
        }
        return work.scope == "complete" ? "English: \(work.translator)"
                                        : "\(work.scope) · English: \(work.translator)"
    }

    // MARK: Credits

    private func credits(_ language: LibraryLanguage) -> String {
        switch language {
        case .greek: return Self.greekCredits
        case .latin: return Self.latinCredits
        case .oldEnglish: return Self.oldEnglishCredits
        case .hebrew: return Self.hebrewCredits
        case .sanskrit: return Self.sanskritCredits
        case .coptic: return Self.copticCredits
        }
    }

    private static let greekCredits = "Texts, translations and treebank from the Perseus Digital Library, Tufts University (CC BY-SA). Euripides: Murray's text with E. P. Coleridge's translation (Bacchae: T. A. Buckley's). Aristophanes: Hall and Geldart's text, with W. J. Hickie's translation of Clouds and an anonymous translation (1912) of Birds. Apollodorus: Frazer's text and translation (Loeb, 1921), with the Perseus treebank of Library 1.1–1.4. Marcus Aurelius: Leopold's text from the Perseus Digital Library (CC BY-SA), parsed with Morpheus; George Long's translation (1862, public domain) from Project Gutenberg. Treebanks of Plato's Apology and Crito, Thucydides and Josephus from Vanessa Gorman's Greek dependency treebanks (CC BY-SA). LSJ, Middle Liddell and short definitions in the Logeion editions by Helma Dik (CC BY-SA). Autenrieth's Homeric Dictionary from the Perseus Digital Library (CC BY-SA). Septuagint: Swete's text as transcribed by the First1KGreek project (CC BY-SA 4.0), parsed automatically with Morpheus, with the Updated Brenton English Septuagint (CC0). New Testament: the SBL Greek New Testament (Society of Biblical Literature and Logos Bible Software, CC BY 4.0), with lemmas and morphology from the MACULA Greek Linguistic Datasets (Biblica, CC BY 4.0), the Berean Standard Bible (public domain) and Abbott-Smith's Manual Greek Lexicon of the New Testament (public domain). Gospel of Nicodemus (Acts of Pilate, Greek recension A, and the Descent into Hell): Tischendorf's text (Evangelia Apocrypha, 2nd ed., 1876; public domain), transcribed for this app from the scan at the Internet Archive and parsed automatically with Morpheus; English: Alexander Walker's translation (Ante-Nicene Fathers 8, 1886; public domain), from Wikisource. Gentium Book Plus by SIL (OFL)."
    private static let latinCredits = "Aeneid: text (Greenough) and translation (Theodore C. Williams) from the Perseus Digital Library (CC BY-SA), parsed with the Perseus Latin Dependency Treebank (6.1–295) and Morpheus. Vulgate: the Clementine Vulgate and the Douay-Rheims Bible (Challoner), public domain; parses from the PROIEL treebank of Jerome's Vulgate (Dag Haug et al., CC BY-NC-SA 4.0) for most of the New Testament, Morpheus elsewhere. Caesar's Gallic War (Holmes's text; W. A. McDevitte and W. S. Bohn's translation), parsed with the PROIEL treebank (CC BY-NC-SA 4.0) for much of Books 1–6; Ovid's Metamorphoses (Magnus's text; Brookes More's translation, 1922), Cicero's In Catilinam (Clark; C. D. Yonge) and De Amicitia (W. A. Falconer, Loeb), Tacitus's Agricola, Germania and Annals 1 (Furneaux and Fisher; A. J. Church and W. J. Brodribb), from the Perseus Digital Library (CC BY-SA), parsed with the Perseus Latin Dependency Treebank where it covers them (Metamorphoses 1, In Catilinam 1–2) and Morpheus. Homer in Latin (Iliad, Odyssey, Hymns): the word-for-word version printed with the Greek in the Didot edition (Paris, 1837–38), from the Project Gutenberg transcription (public domain), parsed with Morpheus, with A. T. Murray's English and the Greek as its parallel text. Lewis & Short's Latin Dictionary, Lewis's Elementary Latin Dictionary and short definitions from the Perseus Digital Library and Logeion (Helma Dik) (CC BY-SA)."
    private static let copticCredits = "Gospel of Thomas: text and annotation from Coptic SCRIPTORIUM (CC BY). Acts of Pilate (two fragments of a White Monastery codex, after Lacau 1904): text and annotation from Coptic SCRIPTORIUM (Lydia Bremer-McCollum, Nicholas Wagner; CC BY 4.0). Nag Hammadi and Berlin Codex texts and Crum's Coptic Dictionary from Marcion by Milan Konvička (GPL), analysed automatically with the Coptic SCRIPTORIUM NLP tools. Sahidic New Testament: Sahidic Bible 2 (Christian Askeland, Matthias Schulz; INTF Münster), CC BY-SA, transcribing the principal manuscripts, with the verses they lack from G. W. Horner's edition (1911–24, public domain), analysed automatically with the Coptic SCRIPTORIUM NLP tools; English from the Berean Standard Bible. Comprehensive Coptic Lexicon by BBAW and DDGLC via KELLIA (CC BY-SA). Noto Sans Coptic by Google (OFL)."
    private static let oldEnglishCredits = "Beowulf: Fr. Klaeber's text (1922) and glossary, and James M. Garnett's translation (1882), from the Perseus Digital Library (CC BY-SA); lemmas and parses taken from Klaeber's glossary. The other poems: The Anglo-Saxon Poetic Records, ed. G. P. Krapp and E. V. K. Dobbie, in Greg Hidley's electronic text (Oxford Text Archive, CC BY-SA), as collected by the Classical Language Toolkit; lemmas and parses automatic, from Beowulf and Ondřej Tichý's Old English morphological generator (CC BY 4.0). English, from Project Gutenberg (public domain): Cosette Faust and Stith Thompson, Old English Poems (1918); James M. Garnett, Elene, Judith, Brunanburh, Maldon and The Dream of the Rood (1889); Robert Kilburn Root, Andreas (1899); James Hall Pitman, The Old English Physiologus (1921). Bosworth and Toller's Anglo-Saxon Dictionary (1898) and Supplement (1921), public domain, from the Germanic Lexicon Project, as assembled by Madeleine Thompson's btc_anglo_saxon (MIT). Gentium Book Plus by SIL (OFL)."
    private static let hebrewCredits = "Hebrew Bible: the Westminster Leningrad Codex (public domain), with lemmas and morphology from the Open Scriptures Hebrew Bible (CC BY 4.0); Brown–Driver–Briggs and Strong's dictionaries from the Open Scriptures Hebrew Lexicon (CC BY 4.0; text public domain); short definitions from STEPBible's Translators Brief Lexicon (TBESH, CC BY 4.0); English from the Berean Standard Bible (public domain). Noto Serif Hebrew by Google (OFL)."
    private static let sanskritCredits = "Bhagavad Gītā: text, lemmas and analyses from the Digital Corpus of Sanskrit by Oliver Hellwig (CC BY 4.0), the critical edition's text; verse numbers from the gita/gita dataset (the Unlicense); English: Annie Besant's translation (4th edition, 1922; public domain), from Wikisource. Upaniṣads: text, lemmas and analyses from the Digital Corpus of Sanskrit (CC BY 4.0); sections numbered from the mūla text of Śaṅkara's commentaries (GRETIL) and from Sanskrit Wikisource, which also supply the few passages DCS lacks (shown unanalysed); English: F. Max Müller, The Upanishads (Sacred Books of the East 1 and 15, 1879–84; public domain), from sacred-texts.com. Macdonell's Practical Sanskrit Dictionary (1893) and Monier-Williams's Sanskrit-English Dictionary (1899) from the Cologne Digital Sanskrit Dictionaries (CC BY-SA 4.0); short definitions from the Digital Corpus of Sanskrit. Gentium Book Plus by SIL (OFL)."
}
