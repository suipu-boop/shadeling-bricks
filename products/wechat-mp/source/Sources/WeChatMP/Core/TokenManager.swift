import Foundation

/// access_token 管理器：缓存 + 过期自动刷新 + 并发去重 + 失效重试支撑。
///
/// 微信 access_token 有效期 7200 秒，且**同一账号并发获取会互相顶掉**，
/// 因此这里用 actor 串行化，并对并发请求做 in-flight 去重。
actor TokenManager {
    static let shared = TokenManager()

    /// 提前 5 分钟视为过期，规避边界失效
    private static let expiryLeeway: TimeInterval = 300

    private struct CachedToken {
        let value: String
        let expiresAt: Date

        var isValid: Bool {
            Date().addingTimeInterval(TokenManager.expiryLeeway) < expiresAt
        }
    }

    private var cached: CachedToken?
    private var inFlight: Task<CachedToken, Error>?

    /// 取可用 token。`forceRefresh` 为 true 时强制重新拉取（用于 40001 / 42001 重试）。
    func token(forceRefresh: Bool = false) async throws -> String {
        if !forceRefresh, let current = cached, current.isValid {
            return current.value
        }
        // 已有刷新任务在进行：复用它，避免并发顶号
        if let inFlight {
            let fresh = try await inFlight.value
            return fresh.value
        }

        let task = Task<CachedToken, Error> {
            let (value, expiresIn) = try await Self.requestToken()
            return CachedToken(
                value: value,
                expiresAt: Date().addingTimeInterval(TimeInterval(expiresIn))
            )
        }
        inFlight = task

        do {
            let fresh = try await task.value
            cached = fresh
            inFlight = nil
            return fresh.value
        } catch {
            inFlight = nil
            throw error
        }
    }

    /// 主动失效本地缓存（收到 token 失效类错误码时调用）
    func invalidate() {
        cached = nil
    }

    /// 缓存剩余有效秒数（仅用于界面展示，nil 表示当前无缓存）
    func remainingLifetime() -> Int? {
        guard let current = cached, current.isValid else { return nil }
        return max(0, Int(current.expiresAt.timeIntervalSinceNow))
    }

    // MARK: - 私有

    /// GET /cgi-bin/token
    private static func requestToken() async throws -> (String, Int) {
        let config = CredentialStore.shared.load()
        guard config.isComplete else { throw WeChatAPIError.notConfigured }

        guard var components = URLComponents(string: WeChatAPI.host + "/cgi-bin/token") else {
            throw WeChatAPIError.invalidURL
        }
        components.queryItems = [
            URLQueryItem(name: "grant_type", value: "client_credential"),
            URLQueryItem(name: "appid", value: config.appID),
            URLQueryItem(name: "secret", value: config.appSecret)
        ]
        guard let url = components.url else { throw WeChatAPIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 20

        let payload = try await WeChatAPI.perform(request)
        if let code = payload["errcode"] as? Int, code != 0 {
            throw WeChatAPIError.api(code: code, message: (payload["errmsg"] as? String) ?? "")
        }
        guard let token = payload["access_token"] as? String, !token.isEmpty else {
            throw WeChatAPIError.malformedResponse
        }
        let expiresIn = (payload["expires_in"] as? Int) ?? 7200
        return (token, expiresIn)
    }
}
