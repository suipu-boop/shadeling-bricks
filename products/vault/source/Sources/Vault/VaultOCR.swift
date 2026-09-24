import Foundation
import Vision
import PDFKit
import AppKit

/// Vault 证件 OCR：从拖入的图片 / PDF 首页识别文本，并尽力抽取结构化字段。
/// 纯本地、不联网（从 Shadeling 底座原样迁移）。
enum VaultOCR {

    /// 同步识别（CPU 密集，调用方应置于后台线程）。
    static func recognize(from url: URL) -> String {
        guard let cg = cgImage(from: url) else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLanguages = ["zh-Hans", "en"]
        request.usesLanguageCorrection = true
        request.recognitionLevel = .accurate
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: "\n")
    }

    /// 从 OCR 文本抽证件字段（尽力而为）。
    static func parseDocumentFields(_ text: String) -> [String: String] {
        var f: [String: String] = [:]
        let typeRules: [(keys: [String], value: String)] = [
            (["居民身份证", "身份证"], "身份证"),
            (["护照"], "护照"),
            (["驾驶证", "驾照"], "驾驶证"),
            (["往来港澳"], "往来港澳通行证"),
            (["台湾居民来往大陆通行证", "台胞证"], "台湾居民来往大陆通行证"),
            (["资格证", "执业证", "从业资格"], "资格证"),
        ]
        for (keys, value) in typeRules {
            if keys.contains(where: { text.contains($0) }) { f["doc_type"] = value; break }
        }
        let dates = extractDates(text)
        if dates.count >= 2 { f["valid_from"] = dates[0]; f["valid_to"] = dates[1] }
        else if dates.count == 1 { f["valid_to"] = dates[0] }
        if let idn = firstMatch(text, pattern: #"[0-9]{17}[0-9Xx]"#) { f["number_full"] = idn }
        return f
    }

    // MARK: - 私有

    private static func cgImage(from url: URL) -> CGImage? {
        let ext = url.pathExtension.lowercased()
        if ext == "pdf" {
            guard let doc = PDFDocument(url: url), let page = doc.page(at: 0) else { return nil }
            let bounds = page.bounds(for: .mediaBox)
            let img = NSImage(size: bounds.size)
            img.lockFocus()
            if let ctx = NSGraphicsContext.current?.cgContext {
                ctx.saveGState()
                ctx.translateBy(x: 0, y: bounds.size.height)
                ctx.scaleBy(x: 1, y: -1)
                page.draw(with: .mediaBox, to: ctx)
                ctx.restoreGState()
            }
            img.unlockFocus()
            return img.cgImage(forProposedRect: nil, context: nil, hints: nil)
        }
        guard let img = NSImage(contentsOf: url),
              let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
        return cg
    }

    private static func extractDates(_ text: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: #"(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})"#) else { return [] }
        let ns = text as NSString
        let ms = re.matches(in: text, range: NSRange(text.startIndex..., in: text))
        return ms.compactMap { r -> String? in
            guard r.numberOfRanges == 4,
                  let y = intIn(ns, r, 1), let mo = intIn(ns, r, 2), let d = intIn(ns, r, 3) else { return nil }
            return String(format: "%04d-%02d-%02d", y, mo, d)
        }
    }

    private static func firstMatch(_ text: String, pattern: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern),
              let r = re.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(r.range, in: text) else { return nil }
        return String(text[range])
    }

    private static func intIn(_ ns: NSString, _ r: NSTextCheckingResult, _ idx: Int) -> Int? {
        guard r.numberOfRanges > idx else { return nil }
        return Int(ns.substring(with: r.range(at: idx)))
    }
}
