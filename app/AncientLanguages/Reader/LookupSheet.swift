import SwiftUI

/// The card that rises when a word is tapped: form, lemma, parse, a one-line
/// gloss, then the full entry in the chosen lexicon. For works without
/// treebank data the parse comes from Morpheus, which lists every possible
/// analysis; the reader picks one (the most likely is first).
struct LookupSheet: View {
    let selection: WordSelection?
    let work: Work
    let library: Library
    /// Highlights that include this word, and what to do with them.
    var annotations: [Annotation] = []
    var onEditAnnotation: (Annotation) -> Void = { _ in }
    var onStartHighlight: () -> Void = {}
    /// Off for words in the parallel text (highlights belong to the work being read).
    var canHighlight = true

    @AppStorage(SettingsKey.lexicon) private var preferredGreek = Lexicon.lsj
    @AppStorage(SettingsKey.copticLexicon) private var preferredCoptic = Lexicon.ccl
    @AppStorage(SettingsKey.homericLexicon) private var preferredHomeric = Lexicon.aut
    @AppStorage(SettingsKey.ntLexicon) private var preferredNT = Lexicon.abs
    @AppStorage(SettingsKey.latinLexicon) private var preferredLatin = Lexicon.ls
    @AppStorage(SettingsKey.oldEnglishLexicon) private var preferredOldEnglish = Lexicon.klaeber
    @AppStorage(SettingsKey.hebrewLexicon) private var preferredHebrew = Lexicon.bdb
    @AppStorage(SettingsKey.sanskritLexicon) private var preferredSanskrit = Lexicon.md
    @AppStorage(SettingsKey.oldNorseLexicon) private var preferredNorse = Lexicon.zoega
    @AppStorage(SettingsKey.devanagari) private var devanagari = false
    @State private var lookup = Lookup()
    @State private var current = Lexicon.lsj
    @State private var analyses: [Analysis] = []
    @State private var chosen = 0
    @State private var grammarRefs: GrammarRefsRequest?
    @Environment(\.openURL) private var openURL
    @Environment(\.dismiss) private var dismiss
    @Environment(AnnotationStore.self) private var store
    @Environment(StudyStore.self) private var study
    @Environment(ModuleManager.self) private var modules

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let selection {
                header(selection)
                if analyses.isEmpty {
                    let parse = ParseFormatter.describe(selection.token.postag)
                    if !parse.isEmpty {
                        HStack(alignment: .firstTextBaseline) {
                            Text(parse).font(.subheadline).foregroundStyle(Color(Palette.speaker))
                            Spacer(minLength: 4)
                            grammarButton
                        }
                    }
                } else {
                    analysisList
                }
                if let gloss = lookup.shortDefinition {
                    Text(gloss).font(.body)
                } else if selection.token.lemma == nil && analyses.isEmpty {
                    Text("No parse is available for this word.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                annotationRow
                if !annotations.isEmpty {
                    HStack { Spacer(); flashcardButton }
                        .font(.callout).buttonStyle(.borderless)
                }
                if Lexicon.available(for: work).isEmpty {
                    dictionaryPrompt
                    Spacer()
                } else {
                    Picker("Lexicon", selection: $current) {
                        ForEach(Lexicon.available(for: work)) { Text($0.shortName).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .padding(.top, 4)
                    EntryWebView(html: entryHTML)
                }
            } else {
                Spacer()
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 18)
        .overlay(alignment: .top) { grabber }
        .background(Color(Palette.paper).ignoresSafeArea())
        .task(id: selection) { reload() }
        .onAppear { chooseLexicon() }
        .onChange(of: library.hasDictionary(language: work.language)) { _, _ in
            // the dictionaries just finished downloading (or were removed)
            chooseLexicon()
            lookupLemma()
        }
        .onChange(of: current) { _, newValue in
            // only a dictionary that's there to pick, so a missing download doesn't reset the choice
            guard Lexicon.available(for: work).contains(newValue) else { return }
            // Homer keeps its own choice, so Autenrieth there doesn't change Plato's default
            if work.isCoptic { preferredCoptic = newValue }
            else if work.isOldNorse { preferredNorse = newValue }
            else if work.isLatin { preferredLatin = newValue }
            else if work.isOldEnglish { preferredOldEnglish = newValue }
            else if work.isHebrew { preferredHebrew = newValue }
            else if work.isSanskrit { preferredSanskrit = newValue }
            else if work.isHomeric { preferredHomeric = newValue }
            else if work.isBible { preferredNT = newValue }
            else { preferredGreek = newValue }
        }
        .onChange(of: chosen) { _, _ in lookupLemma() }
        .sheet(item: $grammarRefs) { request in
            if let store = library.grammar {
                GrammarRefsSheet(store: store, parse: request.parse, refs: request.refs)
                    .presentationDetents([.medium, .large])
            }
        }
    }

    /// The reader's dictionary for this work's language, if it's installed; else the first one that is.
    private func chooseLexicon() {
        let preferred = work.isCoptic ? preferredCoptic : work.isLatin ? preferredLatin
            : work.isOldEnglish ? preferredOldEnglish : work.isOldNorse ? preferredNorse
            : work.isHebrew ? preferredHebrew : work.isSanskrit ? preferredSanskrit
            : work.isHomeric ? preferredHomeric : work.isBible ? preferredNT : preferredGreek
        let available = Lexicon.available(for: work)
        current = available.contains(preferred) ? preferred : (available.first ?? preferred)
    }

    /// In place of the dictionaries when they download separately (Old Norse)
    /// and aren't on the device: the first download failed, or was interrupted.
    @ViewBuilder private var dictionaryPrompt: some View {
        let status = modules.dictionaryStatus[work.language]
        let module = modules.catalog.dictionary(for: work.language)
        VStack(alignment: .leading, spacing: 8) {
            Text("The \(LibraryLanguage(code: work.language)?.label ?? "") dictionaries (\(Lexicon.offered(for: work).map(\.shortName).joined(separator: ", "))) aren't on this device yet.")
                .font(.callout).foregroundStyle(.secondary)
            switch status {
            case .waiting?, .downloading?, .installing?:
                HStack(spacing: 8) {
                    ProgressView()
                    Text(status == .installing ? "Installing…" : "Downloading…")
                        .font(.callout).foregroundStyle(.secondary)
                }
            default:
                if let module, modules.catalog.canDownload(module) {
                    Button {
                        modules.installDictionary(language: work.language)
                    } label: {
                        Label(module.bytes.map {
                            "Download dictionary (\(ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .file)))"
                        } ?? "Download dictionary", systemImage: "arrow.down.circle")
                    }
                    .buttonStyle(.bordered)
                } else {
                    Text("Downloading isn't available in this version.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if case .failed(let why)? = status {
                    Text(why).font(.caption).foregroundStyle(.orange)
                }
            }
        }
        .padding(.top, 8)
    }

    /// Our own grabber (the system one is hidden): tap it to close the card;
    /// dragging it still resizes the sheet.
    private var grabber: some View {
        Capsule()
            .fill(Color(Palette.muted).opacity(0.5))
            .frame(width: 36, height: 5)
            .padding(.top, 6)
            .frame(width: 140, height: 20, alignment: .top)
            .contentShape(Rectangle())
            .onTapGesture { dismiss() }
            .accessibilityLabel("Close")
            .accessibilityAddTraits(.isButton)
    }

    private func header(_ selection: WordSelection) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(work.isSanskrit && devanagari
                 ? "\(Devanagari.transliterate(selection.token.form, joinSandhi: false).text) \(selection.token.form)"
                 : selection.token.form)
                .font(.custom(work.isCoptic ? "NotoSansCoptic-Regular"
                              : work.isHebrew ? "NotoSerifHebrew-Regular" : "GentiumBookPlus", size: 28))
            if let lemma = currentLemma {
                Text("from").font(.callout).foregroundStyle(.secondary)
                Text(lemma).font(work.isCoptic ? .custom("NotoSansCoptic-Regular", size: 22).bold()
                                 : work.isHebrew ? .custom("NotoSerifHebrew-Bold", size: 22)
                                 : .custom("GentiumBookPlus-Bold", size: 22))
            }
            Spacer(minLength: 4)
            Menu {
                Text(PerseusLinks.citation(work: work, cite: selection.cite))
                Button("Copy citation", systemImage: "doc.on.doc") {
                    UIPasteboard.general.string =
                        "\(selection.token.form) (\(PerseusLinks.citation(work: work, cite: selection.cite)))"
                }
                if !work.isCoptic && !work.isOldEnglish && !work.isOldNorse && !work.isSanskrit {
                    if let url = PerseusLinks.wordStudy(form: selection.token.form, latin: work.isLatin) {
                        Button("Perseus Word Study Tool", systemImage: "safari") { openURL(url) }
                    }
                    if let url = PerseusLinks.hopper(work: work, cite: selection.cite) {
                        Button("Open passage in Perseus", systemImage: "safari") { openURL(url) }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(selection.cite).font(.caption.monospacedDigit())
                    Image(systemName: "ellipsis.circle").font(.caption)
                }
                .foregroundStyle(.secondary)
            }
            Button { dismiss() } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2)
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Close")
            .padding(.leading, 4)
        }
    }

    /// This word's highlight and note (if any), or a button to start one.
    @ViewBuilder private var annotationRow: some View {
        if let a = annotations.first {
            Button {
                onEditAnnotation(a)
            } label: {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Circle().fill(Color(a.color.swatch)).frame(width: 10, height: 10)
                    Text(a.hasNote ? a.note : "Highlighted")
                        .font(.callout).lineLimit(2)
                        .foregroundStyle(a.hasNote ? .primary : .secondary)
                    Spacer(minLength: 4)
                    Text(a.hasNote ? "Edit" : "Add note").font(.callout)
                }
            }
            .buttonStyle(.plain)
            .contextMenu {
                Button("Edit", systemImage: "square.and.pencil") { onEditAnnotation(a) }
                if a.hasNote {
                    Button("Delete note (keep highlight)", systemImage: "text.badge.minus") {
                        store.deleteNote(of: a.id)
                    }
                }
                Button(a.hasNote ? "Delete highlight and note" : "Delete highlight",
                       systemImage: "trash", role: .destructive) {
                    store.delete(a.id)
                }
            }
        } else {
            HStack {
                if canHighlight {
                    Button("Highlight…", systemImage: "highlighter", action: onStartHighlight)
                }
                Spacer()
                flashcardButton
            }
            .font(.callout)
            .buttonStyle(.borderless)
        }
    }

    /// The flashcard entry for this word: its dictionary form, or for a second
    /// aorist the aorist itself (as the "My words" deck counts them).
    private var flashcardKey: String? {
        guard let token = selection?.token else { return nil }
        return token.aoristKey ?? token.lemmaKey
    }

    @ViewBuilder private var flashcardButton: some View {
        if let key = flashcardKey, let token = selection?.token {
            if study.isInMyWords(key) {
                Label("In flashcards", systemImage: "checkmark.rectangle.stack")
                    .foregroundStyle(.secondary)
            } else {
                Button("Add to flashcards", systemImage: "rectangle.stack.badge.plus") {
                    study.addToMyWords(key: key, tokenID: token.id, workURN: work.urn)
                }
            }
        }
    }

    /// Morpheus's possible analyses; tap one to look up its lemma.
    private var analysisList: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(analyses.prefix(maxShown).enumerated()), id: \.offset) { i, a in
                Button {
                    chosen = i
                } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Image(systemName: i == chosen ? "largecircle.fill.circle" : "circle")
                            .font(.caption2)
                        Text(a.lemma).font(.custom(work.isCoptic ? "NotoSansCoptic-Regular"
                                                   : work.isHebrew ? "NotoSerifHebrew-Regular" : "GentiumBookPlus",
                                                   size: 16))
                        Text(a.parse).font(.subheadline)
                    }
                    .foregroundStyle(i == chosen ? AnyShapeStyle(Color(Palette.speaker)) : AnyShapeStyle(.secondary))
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
            }
            if analyses.count > maxShown {
                Text("+ \(analyses.count - maxShown) more possible readings")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack(alignment: .firstTextBaseline) {
                Text(caption)
                    .font(.caption2).foregroundStyle(.tertiary)
                Spacer(minLength: 4)
                grammarButton
            }
        }
    }

    // MARK: Grammar

    /// The parse being shown: the treebank's, or the chosen Morpheus reading.
    private var currentParse: String? {
        if analyses.indices.contains(chosen) { return analyses[chosen].parse }
        let p = ParseFormatter.describe(selection?.token.postag)
        return p.isEmpty ? nil : p
    }

    /// The grammar sections on this word's form and use (Greek only, for now).
    private var currentGrammarRefs: [GrammarRef] {
        guard LibraryLanguage(code: work.language) == .greek, let store = library.grammar,
              let parse = currentParse else { return [] }
        let irregular = !analyses.indices.contains(chosen) && selection?.token.aoristKey != nil
        return store.refs(keys: GrammarKeys.keys(parse: parse, irregularAorist: irregular), homeric: work.isHomeric)
    }

    /// "§": opens the sections on this form; hidden when there are none.
    @ViewBuilder private var grammarButton: some View {
        let refs = currentGrammarRefs
        if !refs.isEmpty, let parse = currentParse {
            Button {
                grammarRefs = GrammarRefsRequest(parse: parse, refs: refs)
            } label: {
                Text("§").font(.custom("GentiumBookPlus-Bold", size: 18))
                    .padding(.horizontal, 8).padding(.vertical, 1)
                    .background(Capsule().strokeBorder(Color(Palette.muted).opacity(0.6)))
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color(Palette.speaker))
            .accessibilityLabel("Grammar for this form")
        }
    }

    private var isMorphemes: Bool { ["scriptorium", "coptic-nlp", "oshb", "dcs"].contains(selection?.token.source ?? "") }

    private var caption: String {
        switch selection?.token.source {
        case "scriptorium": return "The parts of this word (Coptic SCRIPTORIUM); tap one to look it up."
        case "coptic-nlp": return "The parts of this word, analysed automatically (Coptic SCRIPTORIUM tools); tap one to look it up."
        case "oshb": return "The parts of this word (Open Scriptures Hebrew Bible); tap one to look it up."
        case "dcs": return analyses.isEmpty ? "Not analysed in the Digital Corpus of Sanskrit."
            : analyses.count > 1 ? "The words joined here by sandhi or compounding (Digital Corpus of Sanskrit); tap one to look it up."
            : "Analysis from the Digital Corpus of Sanskrit."
        case "oe-forms": return "Possible lemmas and parses (automatic: from Beowulf and Tichý's Old English forms); most likely first."
        case "non-forms": return "Possible lemmas and parses (automatic, from Zoëga's headwords); most likely first."
        default: return "Possible parses (Morpheus); most likely first."
        }
    }
    private var maxShown: Int { isMorphemes ? 8 : 4 }

    private var currentLemma: String? {
        if analyses.indices.contains(chosen) { return analyses[chosen].lemma }
        return selection?.token.lemma?.trimmingCharacters(in: .decimalDigits)
    }

    private var currentLemmaKey: String? {
        if analyses.indices.contains(chosen) { return analyses[chosen].lemmaKey }
        return selection?.token.lemmaKey
    }

    private var entryHTML: String {
        let entries = lookup.entries[current] ?? []
        guard !entries.isEmpty else {
            // Autenrieth covers Homer's vocabulary only: fall back to LSJ.
            if current == .aut || current == .abs, let lsj = lookup.entries[.lsj], !lsj.isEmpty {
                return "<p class=\"note\">Not in \(current.shortName); LSJ:</p>"
                    + lsj.map { "<div class=\"entry\">\($0.html)</div>" }.joined(separator: "<hr>")
            }
            // Macdonell is a shorter dictionary: fall back to Monier-Williams.
            if current == .md, let mw = lookup.entries[.mw], !mw.isEmpty {
                return "<p class=\"note\">Not in Macdonell; Monier-Williams:</p>"
                    + mw.map { "<div class=\"entry\">\($0.html)</div>" }.joined(separator: "<hr>")
            }
            // so is Zoëga: fall back to Cleasby–Vigfússon
            if current == .zoega, let cv = lookup.entries[.cleasby], !cv.isEmpty {
                return "<p class=\"note\">Not in Zoëga; Cleasby–Vigfússon:</p>"
                    + cv.map { "<div class=\"entry\">\($0.html)</div>" }.joined(separator: "<hr>")
            }
            return "<p class=\"none\">No entry found in \(current.shortName).</p>"
        }
        return entries.map { entry in
            let note = entry.match == "exact" ? "" :
                "<p class=\"note\">Closest entry (\(Self.matchNote(entry.match))).</p>"
            return note + "<div class=\"entry\">\(entry.html)</div>"
        }.joined(separator: "<hr>")
    }

    private static func matchNote(_ match: String) -> String {
        switch match {
        case "alias": return "listed under a related headword"
        case "form": return "found through one of its forms"
        default: return "matched ignoring accents"
        }
    }

    private func reload() {
        chosen = 0
        analyses = []
        if let selection, let texts = library.texts {
            switch selection.token.source {
            case "morpheus":
                analyses = texts.analyses(of: selection.token.form)
            case "oe-forms":
                // stored under "ang:" so they never mix with Latin's analyses of the same spelling
                analyses = texts.analyses(of: "ang:" + selection.token.form)
            case "non-forms":
                // likewise under "non:"
                analyses = texts.analyses(of: "non:" + selection.token.form)
            case "scriptorium", "coptic-nlp", "oshb", "dcs":
                analyses = texts.morphs(ofToken: selection.token.id)
                // start on the word's main morpheme (its noun or verb)
                chosen = analyses.firstIndex(where: { $0.lemmaKey == selection.token.lemmaKey }) ?? 0
            default:
                break
            }
        }
        lookupLemma()
    }

    private func lookupLemma() {
        guard let key = currentLemmaKey else {
            lookup = Lookup()
            return
        }
        let tag = analyses.indices.contains(chosen) ? analyses[chosen].tag : selection?.token.postag
        lookup = library.lookup(lemmaKey: key, partOfSpeech: work.isCoptic ? tag : nil)
    }
}

/// What the lookup card's "§" opens.
struct GrammarRefsRequest: Identifiable {
    let parse: String
    let refs: [GrammarRef]
    var id: String { parse }
}
