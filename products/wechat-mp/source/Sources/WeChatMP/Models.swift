import Foundation

/// 已上传的永久素材（图片）。
struct MediaAsset: Identifiable, Codable, Equatable {
    /// 微信返回的 media_id，可直接用作草稿封面 thumb_media_id
    let mediaID: String
    /// 微信图床 URL（https://mmbiz.qpic.cn/...）
    let imageURL: String
    /// 本地文件名（仅用于界面辨识）
    let fileName: String
    let uploadedAt: Date

    var id: String { mediaID }
}

/// 草稿列表项。
struct DraftSummary: Identifiable, Equatable {
    let mediaID: String
    let title: String
    let author: String
    let digest: String
    let updateTime: Date?
    let coverURL: String?

    var id: String { mediaID }

    var displayTime: String {
        guard let updateTime else { return "—" }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.string(from: updateTime)
    }
}

/// 待创建的草稿内容。
struct DraftPayload: Equatable {
    var title: String = ""
    var author: String = ""
    var digest: String = ""
    /// 微信兼容的正文 HTML 片段
    var contentHTML: String = ""
    /// 封面素材 ID（必填：草稿接口要求封面）
    var thumbMediaID: String = ""
    var contentSourceURL: String = ""
    var showCoverPic: Bool = true
    var needOpenComment: Bool = false
    var onlyFansCanComment: Bool = false

    var trimmedTitle: String {
        title.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// 是否具备创建草稿的最小条件（标题 + 正文 + 封面）
    var isReady: Bool {
        !trimmedTitle.isEmpty
            && !contentHTML.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !thumbMediaID.isEmpty
    }

    var missingItems: [String] {
        var items: [String] = []
        if trimmedTitle.isEmpty { items.append("标题") }
        if contentHTML.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { items.append("正文") }
        if thumbMediaID.isEmpty { items.append("封面素材") }
        return items
    }

    /// 草稿接口要求的中文字符不转义，JSONSerialization 默认即为 UTF-8 原文输出。
    var jsonObject: [String: Any] {
        [
            "title": trimmedTitle,
            "author": author,
            "digest": digest,
            "content": contentHTML,
            "content_source_url": contentSourceURL,
            "thumb_media_id": thumbMediaID,
            "show_cover_pic": showCoverPic ? 1 : 0,
            "need_open_comment": needOpenComment ? 1 : 0,
            "only_fans_can_comment": onlyFansCanComment ? 1 : 0
        ]
    }
}

/// 发布结果。
struct PublishResult: Equatable {
    let publishID: String
    let articleURL: String?
}

/// 发布权限探测结果。
enum PublishPermission: Equatable {
    /// 尚未探测
    case unknown
    case probing
    /// 具备发布权限
    case granted
    /// 不具备（48001 等）
    case denied(reason: String)

    var isGranted: Bool {
        if case .granted = self { return true }
        return false
    }

    var isDenied: Bool {
        if case .denied = self { return true }
        return false
    }
}
