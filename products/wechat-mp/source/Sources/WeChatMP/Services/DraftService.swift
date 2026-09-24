import Foundation

/// 草稿箱服务。
///
/// 接口（均需 access_token）：
/// - 新增草稿 `POST /cgi-bin/draft/add`
/// - 草稿列表 `POST /cgi-bin/draft/batchget`
/// - 删除草稿 `POST /cgi-bin/draft/delete`
/// - 草稿总数 `GET  /cgi-bin/draft/count`
enum DraftService {
    /// 新增草稿，返回草稿 media_id。
    static func create(_ payload: DraftPayload) async throws -> String {
        guard payload.isReady else {
            throw DraftServiceError.incomplete(missing: payload.missingItems)
        }
        let response = try await WeChatAPI.call(
            path: "/cgi-bin/draft/add",
            method: "POST",
            jsonBody: ["articles": [payload.jsonObject]]
        )
        guard let mediaID = response.stringValue("media_id"), !mediaID.isEmpty else {
            throw WeChatAPIError.malformedResponse
        }
        return mediaID
    }

    /// 草稿列表（offset 从 0 开始，count 取值 1~20）。
    static func list(offset: Int = 0, count: Int = 20) async throws -> [DraftSummary] {
        let response = try await WeChatAPI.call(
            path: "/cgi-bin/draft/batchget",
            method: "POST",
            jsonBody: [
                "offset": max(0, offset),
                "count": min(max(count, 1), 20),
                "no_content": 1
            ]
        )
        let items = response.arrayValue("item") ?? []
        return items.compactMap { item -> DraftSummary? in
            guard let mediaID = item.stringValue("media_id") else { return nil }
            let content = item["content"] as? [String: Any]
            let news = (content?.arrayValue("news_item"))?.first
            let updateSeconds = item.doubleValue("update_time")
                ?? content?.doubleValue("update_time")
            return DraftSummary(
                mediaID: mediaID,
                title: news?.stringValue("title") ?? "(无标题)",
                author: news?.stringValue("author") ?? "",
                digest: news?.stringValue("digest") ?? "",
                updateTime: updateSeconds.map { Date(timeIntervalSince1970: $0) },
                coverURL: news?.stringValue("thumb_url")
            )
        }
    }

    /// 草稿总数。
    static func count() async throws -> Int {
        let response = try await WeChatAPI.call(path: "/cgi-bin/draft/count")
        return response.intValue("total_count") ?? 0
    }

    /// 删除草稿（不可撤销）。
    static func delete(mediaID: String) async throws {
        _ = try await WeChatAPI.call(
            path: "/cgi-bin/draft/delete",
            method: "POST",
            jsonBody: ["media_id": mediaID]
        )
    }
}

enum DraftServiceError: LocalizedError {
    case incomplete(missing: [String])

    var errorDescription: String? {
        switch self {
        case .incomplete(let missing):
            return "草稿信息不完整，请补充：\(missing.joined(separator: "、"))。"
        }
    }
}
