import SwiftUI
import WebKit

/// Renders a dictionary article (HTML produced by the pipeline). WebKit copes
/// with very long entries (λόγος, εἰμί) far better than attributed strings.
struct EntryWebView: UIViewRepresentable {
    let html: String
    /// Tapped links (grammar cross-references: grammar://smyth/439). Without
    /// it, links do nothing.
    var onLink: ((URL) -> Void)? = nil

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        view.navigationDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        context.coordinator.onLink = onLink
        guard context.coordinator.lastHTML != html else { return }
        context.coordinator.lastHTML = html
        // Base URL = bundle resources, so the CSS can load the bundled Gentium fonts.
        view.loadHTMLString(Self.page(html), baseURL: Bundle.main.resourceURL)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var lastHTML: String?
        var onLink: ((URL) -> Void)?

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
            guard action.navigationType == .linkActivated, let url = action.request.url else {
                decisionHandler(.allow)        // our own loadHTMLString
                return
            }
            decisionHandler(.cancel)
            onLink?(url)
        }
    }

    private static func page(_ body: String) -> String {
        """
        <!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
        @font-face { font-family: Gentium; src: url('GentiumBookPlus-Regular.ttf'); }
        @font-face { font-family: Gentium; font-weight: bold; src: url('GentiumBookPlus-Bold.ttf'); }
        @font-face { font-family: Gentium; font-style: italic; src: url('GentiumBookPlus-Italic.ttf'); }
        @font-face { font-family: NotoCoptic; src: url('NotoSansCoptic-Regular.ttf'); }
        .cop { font-family: NotoCoptic, Gentium, serif; }
        .forms { margin: .3em 0 .5em; font-size: .92em; }
        :root { color-scheme: light dark; }
        body { font: 17px/1.45 Gentium, 'Times New Roman', serif; color: #2b261d; background: transparent;
               margin: 0; padding: 6px 0 60px; -webkit-text-size-adjust: none; }
        .hw { font-size: 1.15em; }
        .sense { margin: .4em 0; }
        .sense.l2 { margin-left: .9em; } .sense.l3 { margin-left: 1.8em; } .sense.l4 { margin-left: 2.7em; }
        .sn { color: #6b5a3a; }
        .bibl { color: #8a7d65; }
        .au { font-variant: small-caps; }
        .etym { color: #5b5346; }
        .note, .none { font: 13px -apple-system, sans-serif; color: #8a7d65; }
        hr { border: 0; border-top: 1px solid #d8cdb6; margin: 1em 0; }
        .grammar h4 { font-size: 1em; margin: .7em 0 .3em; }
        .grammar p { margin: .45em 0; }
        .grammar table { border-collapse: collapse; font-size: .92em; margin: .5em 0; }
        .grammar td { padding: 2px 10px 2px 0; vertical-align: top; }
        .grammar ul { padding-left: 1.2em; }
        .sc { font-variant: small-caps; }
        .fn { font-size: .85em; color: #8a7d65; }
        a { color: #6b5a3a; }
        @media (prefers-color-scheme: dark) {
          body { color: #e6e0d6; } .sn { color: #cdb07a; } .bibl, .note, .none { color: #a39274; }
          .etym { color: #c9c0b0; } hr { border-top-color: #4a4336; }
          a { color: #cdb07a; } .fn { color: #a39274; }
        }
        </style></head><body>\(body)</body></html>
        """
    }
}
