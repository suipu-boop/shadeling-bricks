import Foundation

/// 发布服务（freepublish）。
///
/// 权限说明：2025 年 7 月起微信回收了个人主体账号与未认证企业账号的发布接口权限。
/// 本模块先做**只读权限探测**（`freepublish/batchget`），探测不通过时由界面隐藏发布入口。
enum PublishService {
    /// 只读探测当前账号是否具备 freepublish 权限。
    static func probePermission() async -> PublishPermission {
        do {
            _ = try await WeChatAPI.call(
                path: "/cgi-bin/freepublish/batchget",
                method: "POST",
                jsonBody: ["offset": 0, "count": 1, "no_content": 1]
            )
            return .granted
        } catch let error as WeChatAPIError {
            if case .api(let code, let message) = error {
                if WeChatErrorCode.isUnauthorized(code: code) {
                    return .denied(
                        reason: WeChatErrorCode.readableMessage(code: code, apiMessage: message)
                    )
                }
                return .denied(reason: "权限探测失败：\(error.localizedDescription)")
            }
            return .denied(reason: "权限探测失败：\(error.localizedDescription)")
        } catch {
            return .denied(reason: "权限探测失败：\(error.localizedDescription)")
        }
    }

    /// 提交草稿发布（POST /cgi-bin/freepublish/submit）。
    /// - Parameter mediaID: 草稿 media_id
    static func publish(mediaID: String) async throws -> PublishResult {
        let response = try await WeChatAPI.call(
            path: "/cgi-bin/freepublish/submit",
            method: "POST",
            jsonBody: ["media_id": mediaID]
        )
        guard let publishID = response.stringValue("publish_id"), !publishID.isEmpty else {
            throw WeChatAPIError.malformedResponse
        }
        return PublishResult(publishID: publishID, articleURL: nil)
    }

    /// 查询发布状态（POST /cgi-bin/freepublish/get）。
    static func status(publishID: String) async throws -> String {
        let response = try await WeChatAPI.call(
            path: "/cgi-bin/freepublish/get",
            method: "POST",
            jsonBody: ["publish_id": publishID]
        )
        let raw = response.intValue("publish_status") ?? -1
        return statusDescription(raw)
    }

    static func statusDescription(_ status: Int) -> String {
        switch status {
        case 0: return "发布成功"
        case 1: return "发布中，请稍后查询"
        case 2: return "原创校验失败"
        case 3: return "发布失败"
        case 4: return "审核中"
        case 5: return "已删除"
        default: return "未知状态（\(status)）"
        }
    }
}
