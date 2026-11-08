import SwiftUI

/// What the marks in a Coptic text mean: scribes' signs (strokes, the
/// apostrophe, the diaeresis, abbreviation bars) and editors' signs (brackets,
/// underdots). Opened from the reader's passage menu on Coptic works.
struct CopticSignsView: View {
    let work: Work
    @Environment(\.dismiss) private var dismiss

    private struct Sign: Identifiable {
        let sample: String
        let name: String
        let text: String
        var id: String { name }
    }

    private let scribal: [Sign] = [
        Sign(sample: "ⲛ̄  ⲙ̄ⲙⲟϥ  ⲥⲱⲧⲙ̄",
             name: "Supralinear stroke",
             text: "A short stroke over a consonant (or across two) that makes a syllable by itself, with no vowel written: read it with a short, neutral vowel before it. ⲛ̄ is “en”, ⲥⲱⲧⲙ̄ “sōtem”."),
        Sign(sample: "ⲡ⳿  ⲉϥ⳿ϣⲁϫⲉ  ⲡⲉϫⲁϥ̂",
             name: "Apostrophe",
             text: "A small hook written after a consonant, most often ⲡ, ⲧ, ⲕ, ϥ, ϣ or ϭ, usually at the end of a syllable or word. It helped the reader divide the unbroken line of letters and isn't pronounced. Some editions print it as a circumflex over the letter (ⲡⲉϫⲁϥ̂). Common in the Nag Hammadi codices, especially Codex II."),
        Sign(sample: "ⲁⲓ̈  ϩⲁⲓ̈",
             name: "Diaeresis",
             text: "Two dots over ⲓ (sometimes ⲩ), usually where it begins a syllable or follows another vowel. A scribal habit; it doesn't change the sound."),
        Sign(sample: "ⲓ︤ⲥ︥  ⲡⲉⲭ︤ⲥ︥  ⲡ︤ⲛ︥ⲁ",
             name: "Abbreviation bar",
             text: "A bar over a shortened sacred name (nomen sacrum): Jesus, Christ, Spirit, and others. Tap the word to see it in full."),
        Sign(sample: "ⲉ͡ⲓ  ⲟ͡ⲩ",
             name: "Joining arc",
             text: "Printed by some editors (Horner) over two letters read as one sound."),
    ]

    private let editorial: [Sign] = [
        Sign(sample: "ⲁⲩ[ⲱ]",
             name: "Square brackets",
             text: "Letters lost from the manuscript (a hole or worn edge) and restored by the editor."),
        Sign(sample: "ⲉ̣ⲛ̣",
             name: "Dot below",
             text: "A letter only partly preserved, so its reading is uncertain."),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("Written by the scribe") { ForEach(scribal) { row($0) } }
                Section("Added by the editor") { ForEach(editorial) { row($0) } }
                if work.isBible {
                    Section("This edition") {
                        Text("The Sahidic Bible 2 transcriptions don't record the manuscripts’ strokes or diaereses; those shown here are taken from Horner’s edition wherever the two texts have the same letters. The digital Horner lacks strokes in most of Matthew and Revelation, so those books are largely unstroked. Verses missing from the manuscripts (all of Jude, and a few others) are Horner’s text.")
                            .font(.callout)
                    }
                }
            }
            .navigationTitle("Coptic Signs")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private func row(_ sign: Sign) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(sign.sample)
                .font(Font(Fonts.coptic(size: 24)))
            Text(sign.name).font(.headline)
            Text(sign.text).font(.callout).foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
