import Foundation

// MARK: - 数据模型（对齐底座 UIModels.VaultAssetItem / runtime vault_store payload）

/// 一条 vault 资产。解码缺字段给安全默认，不整条丢弃。
struct VaultAsset: Identifiable, Equatable {
    let id: String
    let type: String
    let title: String
    let createdAt: Double
    let updatedAt: Double
    let fileRef: String?
    let hasSensitive: Bool
    let docType: String?
    let issuer: String?
    let validFrom: String?
    let validTo: String?
    let numberMasked: String?
    let desc: String?
    let tags: [String]
    let album: String?
    let url: String?
    let excerpt: String?
    let source: String?
    let skillId: String?
    let version: String?
    let category: String?
    let skillDesc: String?
    let enabled: Bool?
    let text: String?
    let aiSummary: String?
    let aiTags: [String]
    let aiKeyPoints: [String]
    /// payload fields 中未被命名属性覆盖的扩展键值（如账号录入的 account_name）。
    let extra: [String: String]

    /// 是否 AI 自主沉淀渠道写入（source == "ai"），手动录入渠道为 nil/空。
    var isFromAI: Bool { source == "ai" }

    init(id: String, type: String, title: String, createdAt: Double, updatedAt: Double,
         fileRef: String? = nil, hasSensitive: Bool = false,
         docType: String? = nil, issuer: String? = nil, validFrom: String? = nil,
         validTo: String? = nil, numberMasked: String? = nil, desc: String? = nil,
         tags: [String] = [], album: String? = nil, url: String? = nil,
         excerpt: String? = nil, source: String? = nil, skillId: String? = nil,
         version: String? = nil, category: String? = nil, skillDesc: String? = nil,
         enabled: Bool? = nil, text: String? = nil, aiSummary: String? = nil,
         aiTags: [String] = [], aiKeyPoints: [String] = [], extra: [String: String] = [:]) {
        self.id = id; self.type = type; self.title = title
        self.createdAt = createdAt; self.updatedAt = updatedAt
        self.fileRef = fileRef; self.hasSensitive = hasSensitive
        self.docType = docType; self.issuer = issuer; self.validFrom = validFrom
        self.validTo = validTo; self.numberMasked = numberMasked; self.desc = desc
        self.tags = tags; self.album = album; self.url = url; self.excerpt = excerpt
        self.source = source; self.skillId = skillId; self.version = version
        self.category = category; self.skillDesc = skillDesc; self.enabled = enabled
        self.text = text; self.aiSummary = aiSummary; self.aiTags = aiTags
        self.aiKeyPoints = aiKeyPoints; self.extra = extra
    }

    init?(from d: [String: Any]) {
        guard let id = d["id"] as? String, let type = d["type"] as? String else { return nil }
        // 未被命名属性覆盖的扩展键收进 extra（如 account_name）
        let known: Set<String> = ["id", "type", "title", "created_at", "updated_at",
                                  "file_ref", "has_sensitive", "source", "doc_type",
                                  "issuer", "valid_from", "valid_to", "number_masked",
                                  "number_full", "description", "tags", "album", "url",
                                  "excerpt", "skill_id", "version", "category", "desc",
                                  "enabled", "text", "ai_summary", "ai_tags", "ai_key_points"]
        var extra: [String: String] = [:]
        for (k, v) in d where !known.contains(k) {
            if let s = v as? String, !s.isEmpty { extra[k] = s }
        }
        let created = d["created_at"] as? Double ?? 0
        let updated = d["updated_at"] as? Double ?? 0
        let aiSummary = (d["ai_summary"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        self.init(
            id: id, type: type,
            title: (d["title"] as? String) ?? "",
            createdAt: created,
            updatedAt: updated,
            fileRef: d["file_ref"] as? String,
            hasSensitive: d["has_sensitive"] as? Bool ?? false,
            docType: d["doc_type"] as? String,
            issuer: d["issuer"] as? String,
            validFrom: d["valid_from"] as? String,
            validTo: d["valid_to"] as? String,
            numberMasked: d["number_masked"] as? String,
            desc: d["description"] as? String,
            tags: d["tags"] as? [String] ?? [],
            album: d["album"] as? String,
            url: d["url"] as? String,
            excerpt: d["excerpt"] as? String,
            source: d["source"] as? String,
            skillId: d["skill_id"] as? String,
            version: d["version"] as? String,
            category: d["category"] as? String,
            skillDesc: d["desc"] as? String,
            enabled: d["enabled"] as? Bool,
            text: d["text"] as? String,
            aiSummary: aiSummary,
            aiTags: d["ai_tags"] as? [String] ?? [],
            aiKeyPoints: d["ai_key_points"] as? [String] ?? [],
            extra: extra
        )
    }

    /// 账号录入的账户名（存在扩展字段 account_name 中）。
    var notesAccountName: String? { extra["account_name"] }

    /// 卡片副标题（摘要行）。
    var subtitle: String {
        switch type {
        case "document":
            return [docType, validTo.map { "至 \($0)" }]
                .compactMap { $0 }.joined(separator: " · ")
        case "webpage":
            return [source, url].compactMap { $0 }.joined(separator: " · ")
        case "skill_snapshot":
            return [category, version].compactMap { $0 }.joined(separator: " · ")
        case "image":
            return album.map { "相册 · \($0)" } ?? ""
        case "note":
            return text.map { String($0.prefix(60)) } ?? ""
        default:
            return ""
        }
    }
}

/// 手动录入表单的动态字段定义
struct VaultFieldSpec: Identifiable {
    let id: String
    let label: String
    var value: String = ""
    var sensitive: Bool = false
    var placeholder: String = ""
}

/// 录入模板：按类型给出字段清单
enum ManualTemplate {
    static let documentTypeOptions = ["身份证", "驾照", "护照", "资格证", "其他证件"]

    static func spec(for manualKind: ManualKind) -> [VaultFieldSpec] {
        switch manualKind {
        case .document(let docType):
            var specs: [VaultFieldSpec] = [
                .init(id: "doc_type", label: "证件类型", value: docType),
                .init(id: "issuer", label: "签发方", placeholder: "如 XX 市公安局 / XX 公司"),
            ]
            if docType == "身份证" {
                specs.append(.init(id: "number_full", label: "证件号码", sensitive: true,
                                   placeholder: "号码加密存储"))
            } else {
                specs.append(.init(id: "number_full", label: "证件号码", sensitive: true,
                                   placeholder: "号码加密存储"))
            }
            specs.append(contentsOf: [
                .init(id: "valid_from", label: "生效日期", placeholder: "YYYY-MM-DD"),
                .init(id: "valid_to", label: "到期日期", placeholder: "YYYY-MM-DD"),
                .init(id: "description", label: "备注", placeholder: "可选"),
            ])
            return specs
        case .account:
            return [
                .init(id: "account_name", label: "账户名", placeholder: "账号 / 用户名"),
                .init(id: "password", label: "口令", sensitive: true, placeholder: "加密存储"),
                .init(id: "url", label: "网址", placeholder: "登录地址，可选"),
                .init(id: "description", label: "备注", placeholder: "可选"),
            ]
        case .webpage:
            return [
                .init(id: "url", label: "网址", placeholder: "https://…"),
                .init(id: "description", label: "备注", placeholder: "可选"),
            ]
        case .note:
            return [
                .init(id: "text", label: "内容"),
            ]
        }
    }
}

enum ManualKind: Hashable {
    case document(String)
    case account
    case webpage
    case note

    var label: String {
        switch self {
        case .document(let t): return "证件 · \(t)"
        case .account: return "账号"
        case .webpage: return "收藏"
        case .note: return "笔记"
        }
    }

    var type: String {
        switch self {
        case .document: return "document"
        case .account: return "note"
        case .webpage: return "webpage"
        case .note: return "note"
        }
    }
}
