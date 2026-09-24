import Foundation

/// 轻量 Markdown → 微信兼容 HTML 渲染器（零第三方依赖）。
///
/// 支持的语法：标题（# ~ ######）、段落、粗体、斜体、删除线、行内代码、代码块、
/// 引用、无序 / 有序列表、分割线、链接、图片。
/// 输出为 HTML 片段，所有样式内联（微信会剥离 class 与外部样式）。
enum MarkdownRenderer {
    static func render(markdown: String, theme: WeChatTheme) -> String {
        let normalized = markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        let lines = normalized.components(separatedBy: "\n")

        var blocks: [String] = []
        var paragraph: [String] = []
        var index = 0

        func flushParagraph() {
            guard !paragraph.isEmpty else { return }
            let joined = paragraph.joined(separator: "<br/>")
            blocks.append("<p style=\"\(theme.paragraphStyle)\">\(inline(joined, theme: theme))</p>")
            paragraph.removeAll()
        }

        while index < lines.count {
            let line = lines[index]

            // 代码块
            if line.hasPrefix("```") {
                flushParagraph()
                var code: [String] = []
                index += 1
                while index < lines.count, !lines[index].hasPrefix("```") {
                    code.append(lines[index])
                    index += 1
                }
                index += 1 // 跳过结束围栏
                let escaped = escapeHTML(code.joined(separator: "\n"))
                blocks.append("<pre style=\"\(theme.codeBlockStyle)\"><code>\(escaped)</code></pre>")
                continue
            }

            // 空行 → 段落分隔
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                flushParagraph()
                index += 1
                continue
            }

            // 分割线
            if isDivider(line) {
                flushParagraph()
                blocks.append("<hr style=\"\(theme.dividerStyle)\"/>")
                index += 1
                continue
            }

            // 标题
            if let heading = parseHeading(line) {
                flushParagraph()
                let content = inline(escapeHTML(heading.text), theme: theme)
                blocks.append("<section style=\"\(theme.headingStyle(level: heading.level))\">\(content)</section>")
                index += 1
                continue
            }

            // 引用（连续行合并为一个 blockquote）
            if line.trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                flushParagraph()
                var quote: [String] = []
                while index < lines.count,
                      lines[index].trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                    quote.append(stripQuoteMarker(lines[index]))
                    index += 1
                }
                let joined = quote.joined(separator: "<br/>")
                blocks.append("<blockquote style=\"\(theme.quoteStyle)\">\(inline(joined, theme: theme))</blockquote>")
                continue
            }

            // 列表
            if let marker = listMarker(line) {
                flushParagraph()
                var items: [String] = []
                var ordered = marker.ordered
                while index < lines.count, let current = listMarker(lines[index]) {
                    items.append(inline(escapeHTML(current.text), theme: theme))
                    ordered = current.ordered
                    index += 1
                }
                let tag = ordered ? "ol" : "ul"
                let rendered = items
                    .map { "<li style=\"\(theme.listItemStyle)\">\($0)</li>" }
                    .joined()
                blocks.append("<\(tag) style=\"\(theme.listContainerStyle)\">\(rendered)</\(tag)>")
                continue
            }

            // 独占一行的图片
            if isStandaloneImage(line) {
                flushParagraph()
                blocks.append("<p style=\"margin:0 0 \(theme.paragraphSpacing)px;\">\(inline(escapeHTML(line), theme: theme))</p>")
                index += 1
                continue
            }

            paragraph.append(line)
            index += 1
        }

        flushParagraph()
        return "<section style=\"\(theme.bodyStyle)\">\n\(blocks.joined(separator: "\n"))\n</section>"
    }

    // MARK: - 块级解析辅助

    private static func isDivider(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 3 else { return false }
        return trimmed.allSatisfy { $0 == "-" } || trimmed.allSatisfy { $0 == "*" } || trimmed.allSatisfy { $0 == "_" }
    }

    private static func parseHeading(_ line: String) -> (level: Int, text: String)? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("#") else { return nil }
        let hashes = trimmed.prefix { $0 == "#" }
        let level = hashes.count
        guard (1...6).contains(level) else { return nil }
        let text = String(trimmed.dropFirst(level)).trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return (level, text)
    }

    private static func stripQuoteMarker(_ line: String) -> String {
        var trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix(">") {
            trimmed.removeFirst()
            trimmed = trimmed.trimmingCharacters(in: .whitespaces)
        }
        return trimmed
    }

    private static func listMarker(_ line: String) -> (ordered: Bool, text: String)? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        // 无序列表
        for marker in ["- ", "* ", "+ "] where trimmed.hasPrefix(marker) {
            return (false, String(trimmed.dropFirst(marker.count)))
        }
        // 有序列表
        let digits = trimmed.prefix { $0.isNumber }
        if !digits.isEmpty {
            let rest = trimmed.dropFirst(digits.count)
            if rest.hasPrefix(". ") || rest.hasPrefix("、") {
                let text = rest.hasPrefix(". ") ? String(rest.dropFirst(2)) : String(rest.dropFirst(1))
                return (true, text)
            }
        }
        return nil
    }

    private static func isStandaloneImage(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        return trimmed.hasPrefix("![") && trimmed.hasSuffix(")") && trimmed.contains("](")
    }

    // MARK: - 行内解析

    private static func escapeHTML(_ text: String) -> String {
        text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }

    private static func inline(_ text: String, theme: WeChatTheme) -> String {
        var result = text
        result = replace(result, pattern: "!\\[([^\\]]*)\\]\\(([^\\)\\s]+)\\)") { match in
            let alt = match.count > 1 ? match[1] : ""
            let src = match.count > 2 ? match[2] : ""
            return "<img src=\"\(src)\" alt=\"\(alt)\" style=\"\(theme.imageStyle)\"/>"
        }
        result = replace(result, pattern: "\\[([^\\]]+)\\]\\(([^\\)\\s]+)\\)") { match in
            let title = match.count > 1 ? match[1] : ""
            let href = match.count > 2 ? match[2] : ""
            return "<a href=\"\(href)\" style=\"\(theme.linkStyle)\">\(title)</a>"
        }
        result = replace(result, pattern: "\\*\\*([^*]+)\\*\\*") { match in
            "<strong>\(match.count > 1 ? match[1] : "")</strong>"
        }
        result = replace(result, pattern: "~~([^~]+)~~") { match in
            "<del>\(match.count > 1 ? match[1] : "")</del>"
        }
        result = replace(result, pattern: "`([^`]+)`") { match in
            "<code style=\"\(theme.inlineCodeStyle)\">\(match.count > 1 ? match[1] : "")</code>"
        }
        result = replace(result, pattern: "\\*([^*]+)\\*") { match in
            "<em>\(match.count > 1 ? match[1] : "")</em>"
        }
        return result
    }

    /// 基于 NSRegularExpression 的替换，捕获组通过闭包回传（下标 0 为整体匹配）。
    private static func replace(
        _ text: String,
        pattern: String,
        transform: ([String]) -> String
    ) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
        let nsText = text as NSString
        let matches = regex.matches(in: text, range: NSRange(location: 0, length: nsText.length))
        guard !matches.isEmpty else { return text }

        var output = ""
        var cursor = 0
        for match in matches {
            let range = match.range
            output += nsText.substring(with: NSRange(location: cursor, length: range.location - cursor))
            var groups: [String] = []
            for groupIndex in 0..<match.numberOfRanges {
                let groupRange = match.range(at: groupIndex)
                groups.append(groupRange.location == NSNotFound ? "" : nsText.substring(with: groupRange))
            }
            output += transform(groups)
            cursor = range.location + range.length
        }
        output += nsText.substring(from: cursor)
        return output
    }
}
