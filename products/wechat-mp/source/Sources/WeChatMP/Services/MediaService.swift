import Foundation

/// 永久素材服务：图片上传 + 本地素材库缓存。
enum MediaService {
    /// 单张图片上限 10 MB（微信永久素材图片限制）
    static let maxImageBytes = 10 * 1024 * 1024

    /// 上传图片到永久素材（POST /cgi-bin/material/add_material?type=image）。
    /// - Returns: 含 media_id 与图片 URL 的素材记录
    static func uploadImage(fileURL: URL) async throws -> MediaAsset {
        let data: Data
        do {
            data = try Data(contentsOf: fileURL)
        } catch {
            throw WeChatAPIError.transport(error)
        }
        guard data.count <= maxImageBytes else {
            throw MediaUploadError.tooLarge(bytes: data.count)
        }

        let filename = fileURL.lastPathComponent
        let mimeType = Self.mimeType(for: fileURL.pathExtension)

        let payload = try await WeChatAPI.upload(
            path: "/cgi-bin/material/add_material",
            queryItems: [URLQueryItem(name: "type", value: "image")],
            fileField: "media",
            filename: filename,
            mimeType: mimeType,
            fileData: data
        )

        guard let mediaID = payload.stringValue("media_id"), !mediaID.isEmpty else {
            throw WeChatAPIError.malformedResponse
        }
        return MediaAsset(
            mediaID: mediaID,
            imageURL: payload.stringValue("url") ?? "",
            fileName: filename,
            uploadedAt: Date()
        )
    }

    /// 上传「图文消息内图片」（POST /cgi-bin/media/uploadimg），不占用素材库配额，
    /// 返回可直接在正文中使用的图片 URL。
    static func uploadInlineImage(fileURL: URL) async throws -> String {
        let data: Data
        do {
            data = try Data(contentsOf: fileURL)
        } catch {
            throw WeChatAPIError.transport(error)
        }
        let payload = try await WeChatAPI.upload(
            path: "/cgi-bin/media/uploadimg",
            filename: fileURL.lastPathComponent,
            mimeType: Self.mimeType(for: fileURL.pathExtension),
            fileData: data
        )
        guard let url = payload.stringValue("url"), !url.isEmpty else {
            throw WeChatAPIError.malformedResponse
        }
        return url
    }

    private static func mimeType(for pathExtension: String) -> String {
        switch pathExtension.lowercased() {
        case "png": return "image/png"
        case "gif": return "image/gif"
        case "bmp": return "image/bmp"
        case "webp": return "image/webp"
        default: return "image/jpeg"
        }
    }
}

enum MediaUploadError: LocalizedError {
    case tooLarge(bytes: Int)

    var errorDescription: String? {
        switch self {
        case .tooLarge(let bytes):
            let mb = Double(bytes) / 1024 / 1024
            return String(format: "图片 %.1f MB 超过微信永久素材 10 MB 上限，请压缩后重试。", mb)
        }
    }
}

/// 本地素材库：缓存已上传素材，落盘到应用私有目录（不含任何凭据）。
enum MediaLibrary {
    private static var fileURL: URL {
        CredentialStore.shared.storageDirectory.appendingPathComponent("media-library.json")
    }

    static func load() -> [MediaAsset] {
        guard let data = try? Data(contentsOf: fileURL),
              let items = try? JSONDecoder().decode([MediaAsset].self, from: data) else {
            return []
        }
        return items
    }

    @discardableResult
    static func save(_ items: [MediaAsset]) -> Bool {
        let directory = CredentialStore.shared.storageDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let data = try? JSONEncoder().encode(items) else { return false }
        do {
            try data.write(to: fileURL, options: [.atomic])
            return true
        } catch {
            return false
        }
    }

    static func appending(_ asset: MediaAsset, to items: [MediaAsset]) -> [MediaAsset] {
        var merged = items.filter { $0.mediaID != asset.mediaID }
        merged.insert(asset, at: 0)
        return merged
    }
}
