import Foundation

/// 网络层 / 接口层统一错误。
enum WeChatAPIError: LocalizedError {
    /// 账号尚未配置（AppID / AppSecret 为空）
    case notConfigured
    /// URL 组装失败
    case invalidURL
    /// 传输层失败（超时、断网、TLS 等）
    case transport(Error)
    /// HTTP 状态码异常
    case httpStatus(Int)
    /// 响应体不是合法 JSON 对象
    case malformedResponse
    /// 接口返回 errcode != 0
    case api(code: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "尚未配置公众号凭据，请先在「账号」页填写 AppID 与 AppSecret。"
        case .invalidURL:
            return "请求地址组装失败。"
        case .transport(let error):
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain {
                switch ns.code {
                case NSURLErrorTimedOut:
                    return "请求超时：网络较慢或被中断，请重试。"
                case NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost:
                    return "网络不可用：请检查本机网络连接。"
                case NSURLErrorCannotFindHost, NSURLErrorCannotConnectToHost:
                    return "无法连接 api.weixin.qq.com：请检查网络或 DNS。"
                case NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateUntrusted:
                    return "TLS 握手失败：请检查系统时间与证书信任设置。"
                default:
                    break
                }
            }
            return "网络请求失败：\(ns.localizedDescription)"
        case .httpStatus(let code):
            return "服务端返回异常状态码 HTTP \(code)。"
        case .malformedResponse:
            return "响应内容无法解析为 JSON。"
        case .api(let code, let message):
            return WeChatErrorCode.readableMessage(code: code, apiMessage: message)
        }
    }
}

/// 微信公众号接口错误码 → 中文可读提示。
enum WeChatErrorCode {
    /// 触发 access_token 自动刷新重试的错误码
    static let tokenExpiredCodes: Set<Int> = [40001, 42001]

    /// 无权限类错误码（用于发布权限探测）
    static let unauthorizedCodes: Set<Int> = [48001, 48002, 40164, 40165]

    static func readableMessage(code: Int, apiMessage: String) -> String {
        let detail = apiMessage.isEmpty ? "" : "（\(apiMessage)）"
        switch code {
        case 40001:
            return "access_token 无效或已过期\(detail)：应用已尝试自动刷新，若仍失败请检查 AppID / AppSecret。"
        case 40007:
            return "无效的 media_id\(detail)：封面或素材不存在、或不属于当前账号，请重新上传素材。"
        case 40008:
            return "消息长度超限\(detail)：请精简标题或正文后重试。"
        case 40013:
            return "AppID 无效\(detail)：请核对后台「设置与开发 → 基本配置」中的 AppID。"
        case 40125:
            return "AppSecret 无效\(detail)：请在后台重置开发者密码后重新填写。"
        case 40164:
            return "调用来源 IP 不在白名单\(detail)：请把本机公网 IP 加入「设置与开发 → 基本配置 → IP 白名单」。"
        case 40165:
            return "无效 IP\(detail)：白名单尚未生效或本机出口 IP 已变化，更新后约 5 分钟重试。"
        case 42001:
            return "access_token 已过期\(detail)：应用已尝试自动刷新。"
        case 45002:
            return "内容超长\(detail)：标题或正文超出接口限制。"
        case 45009:
            return "接口调用频次超限\(detail)：请稍后重试。"
        case 48001:
            return "api 功能未授权\(detail)：当前账号类型或认证状态不支持该接口（发布接口 freepublish 需已认证的企业订阅号或服务号）。"
        case 48002:
            return "粉丝拒收消息\(detail)。"
        case 50002:
            return "用户受限\(detail)：账号状态异常，请检查公众平台后台。"
        default:
            return "接口返回错误 errcode \(code)\(detail)。"
        }
    }

    /// 是否为「无权限」类错误（用于隐藏发布入口）
    static func isUnauthorized(code: Int) -> Bool {
        unauthorizedCodes.contains(code)
    }
}
