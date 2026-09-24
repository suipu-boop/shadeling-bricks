import SwiftUI
import WebKit

/// 微信兼容 HTML 预览（WKWebView 承载渲染结果）。
struct HTMLPreviewView: NSViewRepresentable {
    let html: String

    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.setValue(false, forKey: "drawsBackground")
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        nsView.loadHTMLString(Self.wrap(html), baseURL: nil)
    }

    /// 模拟手机阅读宽度（约 420pt），便于判断真实观感。
    private static func wrap(_ fragment: String) -> String {
        """
        <!doctype html>
        <html>
        <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
          html, body { margin: 0; padding: 0; background: #ffffff; }
          .page { max-width: 420px; margin: 0 auto; padding: 20px 18px 60px; }
        </style>
        </head>
        <body><div class="page">\(fragment)</div></body>
        </html>
        """
    }
}
