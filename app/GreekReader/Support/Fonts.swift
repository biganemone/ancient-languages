import CoreText
import UIKit

/// Gentium Book Plus (SIL, OFL) is bundled for full polytonic coverage;
/// registering at runtime avoids needing an Info.plist UIAppFonts entry.
enum Fonts {
    static func registerBundledFonts() {
        for url in Bundle.main.urls(forResourcesWithExtension: "ttf", subdirectory: nil) ?? [] {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }

    /// Gentium, falling back to Noto Serif Hebrew (OFL) for Hebrew letters,
    /// vowel points and cantillation (the Hebrew Bible, and Hebrew words in
    /// the lexica), which Gentium doesn't have.
    static func greek(size: CGFloat) -> UIFont {
        guard let gentium = UIFont(name: "GentiumBookPlus", size: size) else {   // PostScript name of the Regular face
            return UIFont(name: "TimesNewRomanPSMT", size: size) ?? .systemFont(ofSize: size)
        }
        let cascade = gentium.fontDescriptor.addingAttributes([
            .cascadeList: [UIFontDescriptor(fontAttributes: [.name: "NotoSerifHebrew-Regular"])],
        ])
        return UIFont(descriptor: cascade, size: size)
    }

    /// Noto Serif Hebrew, for Hebrew shown on its own (word card headers).
    static func hebrew(size: CGFloat) -> UIFont {
        UIFont(name: "NotoSerifHebrew-Regular", size: size) ?? greek(size: size)
    }

    /// Noto Sans Coptic (Google, OFL): covers the Coptic block and the marks
    /// editions use (supralinear strokes, nomina sacra overlines, underdots).
    static func coptic(size: CGFloat) -> UIFont {
        UIFont(name: "NotoSansCoptic-Regular", size: size) ?? .systemFont(ofSize: size)
    }

    static func text(size: CGFloat, coptic isCoptic: Bool) -> UIFont {
        isCoptic ? coptic(size: size) : greek(size: size)
    }

    static func greekBold(size: CGFloat) -> UIFont {
        UIFont(name: "GentiumBookPlus-Bold", size: size)
            ?? UIFont(name: "TimesNewRomanPS-BoldMT", size: size)
            ?? .boldSystemFont(ofSize: size)
    }
}

/// Paper-like reading colours that follow light/dark mode.
enum Palette {
    static let paper = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.11, green: 0.105, blue: 0.10, alpha: 1)
        : UIColor(red: 0.985, green: 0.972, blue: 0.945, alpha: 1) }
    static let ink = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.90, green: 0.88, blue: 0.84, alpha: 1)
        : UIColor(red: 0.114, green: 0.106, blue: 0.09, alpha: 1) }
    static let muted = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.60, green: 0.57, blue: 0.52, alpha: 1)
        : UIColor(red: 0.60, green: 0.56, blue: 0.49, alpha: 1) }
    static let speaker = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.80, green: 0.68, blue: 0.47, alpha: 1)
        : UIColor(red: 0.42, green: 0.35, blue: 0.23, alpha: 1) }
    static let highlight = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.55, green: 0.43, blue: 0.13, alpha: 1)
        : UIColor(red: 0.953, green: 0.851, blue: 0.541, alpha: 1) }
    static let englishBackground = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(white: 1, alpha: 0.05)
        : UIColor(red: 0.957, green: 0.937, blue: 0.890, alpha: 1) }
}
