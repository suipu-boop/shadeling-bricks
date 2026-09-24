import Foundation

/// 微信兼容排版主题。
///
/// 微信编辑器会剥离 `class` 与外部样式表，因此所有样式必须**内联**写入标签的 `style` 属性。
struct WeChatTheme: Identifiable, Hashable {
    enum HeadingStyle: String, Hashable {
        /// 左侧竖线（强调色）
        case bar
        /// 底部细线
        case underline
        /// 纯文字
        case plain
    }

    let id: String
    let name: String
    let summary: String

    let fontFamily: String
    let fontSize: Int
    let lineHeight: Double
    let paragraphSpacing: Int

    let textColor: String
    let secondaryColor: String
    let accentColor: String
    let dividerColor: String
    let quoteBackground: String
    let codeBackground: String

    let headingStyle: HeadingStyle

    // MARK: - 内联样式

    var bodyStyle: String {
        "font-family:\(fontFamily);font-size:\(fontSize)px;line-height:\(lineHeight);color:\(textColor);letter-spacing:0.5px;"
    }

    var paragraphStyle: String {
        "margin:0 0 \(paragraphSpacing)px;font-size:\(fontSize)px;line-height:\(lineHeight);color:\(textColor);"
    }

    var quoteStyle: String {
        "margin:0 0 \(paragraphSpacing)px;padding:12px 16px;border-left:3px solid \(accentColor);"
            + "background:\(quoteBackground);color:\(secondaryColor);font-size:\(fontSize - 1)px;line-height:\(lineHeight);"
    }

    var codeBlockStyle: String {
        "margin:0 0 \(paragraphSpacing)px;padding:14px 16px;background:\(codeBackground);border-radius:6px;"
            + "font-family:Menlo,Consolas,monospace;font-size:\(fontSize - 2)px;line-height:1.6;color:\(textColor);"
            + "white-space:pre-wrap;word-break:break-word;"
    }

    var inlineCodeStyle: String {
        "padding:1px 5px;background:\(codeBackground);border-radius:3px;"
            + "font-family:Menlo,Consolas,monospace;font-size:\(fontSize - 2)px;color:\(accentColor);"
    }

    var linkStyle: String {
        "color:\(accentColor);text-decoration:none;border-bottom:1px solid \(accentColor);"
    }

    var imageStyle: String {
        "max-width:100%;height:auto;border-radius:4px;display:block;margin:0 auto;"
    }

    var dividerStyle: String {
        "border:none;border-top:1px solid \(dividerColor);margin:24px 0;"
    }

    var listItemStyle: String {
        "margin:0 0 6px;font-size:\(fontSize)px;line-height:\(lineHeight);color:\(textColor);"
    }

    var listContainerStyle: String {
        "margin:0 0 \(paragraphSpacing)px;padding-left:22px;"
    }

    /// 标题内联样式（level 为 1~6）
    func headingStyle(level: Int) -> String {
        let size = fontSize + max(0, (7 - min(max(level, 1), 6)) * 2)
        let base = "margin:28px 0 16px;font-size:\(size)px;font-weight:700;line-height:1.4;color:\(textColor);"
        switch headingStyle {
        case .bar:
            return base + "padding-left:12px;border-left:4px solid \(accentColor);"
        case .underline:
            return base + "padding-bottom:8px;border-bottom:1px solid \(dividerColor);"
        case .plain:
            return base
        }
    }

    // MARK: - 内置主题

    static let pine = WeChatTheme(
        id: "pine",
        name: "松绿",
        summary: "绿色强调，标题带竖线，适合资讯 / 技术分享",
        fontFamily: "-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif",
        fontSize: 16,
        lineHeight: 1.8,
        paragraphSpacing: 18,
        textColor: "#2b2b2b",
        secondaryColor: "#5a5a5a",
        accentColor: "#0f7b6c",
        dividerColor: "#e6e6e6",
        quoteBackground: "#f4f8f7",
        codeBackground: "#f5f6f7",
        headingStyle: .bar
    )

    static let plainInk = WeChatTheme(
        id: "plain-ink",
        name: "素墨",
        summary: "黑白极简，标题下划线，适合长文 / 观点表达",
        fontFamily: "-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif",
        fontSize: 16,
        lineHeight: 1.9,
        paragraphSpacing: 20,
        textColor: "#1f1f1f",
        secondaryColor: "#666666",
        accentColor: "#1f1f1f",
        dividerColor: "#e0e0e0",
        quoteBackground: "#fafafa",
        codeBackground: "#f4f4f4",
        headingStyle: .underline
    )

    static let all: [WeChatTheme] = [.pine, .plainInk]

    static var `default`: WeChatTheme { .pine }
}
