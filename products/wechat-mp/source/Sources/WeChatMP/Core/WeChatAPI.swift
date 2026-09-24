import Foundation

/// 微信公众号开放接口网络层（URLSession，仅访问 api.weixin.qq.com，零第三方依赖）。
///
/// 统一负责：
/// 1. 注入 access_token；
/// 2. 遇 40001 / 42001 自动刷新 token 并重试一次；
/// 3. 把 errcode 转换为带中文提示的 `WeChatAPIError`。
enum WeChatAPI {
    static let host = "https://api.weixin.qq.com"

    // MARK: - JSON 调用

    /// 带 token 的 JSON 调用（GET / POST）。
    static func call(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> [String: Any] {
        let body = try jsonBody.map { try JSONSerialization.data(withJSONObject: $0) }
        return try await sendWithToken(
            path: path,
            method: method,
            queryItems: queryItems,
            body: body,
            contentType: body == nil ? nil : "application/json; charset=utf-8"
        )
    }

    // MARK: - multipart 上传（素材）

    /// 带 token 的 multipart/form-data 上传（用于永久素材等接口）。
    static func upload(
        path: String,
        queryItems: [URLQueryItem] = [],
        fileField: String = "media",
        filename: String,
        mimeType: String,
        fileData: Data,
        extraFields: [String: String] = [:]
    ) async throws -> [String: Any] {
        let boundary = "----WeChatMPBoundary\(UUID().uuidString)"
        let body = multipartBody(
            boundary: boundary,
            fileField: fileField,
            filename: filename,
            mimeType: mimeType,
            fileData: fileData,
            extraFields: extraFields
        )
        return try await sendWithToken(
            path: path,
            method: "POST",
            queryItems: queryItems,
            body: body,
            contentType: "multipart/form-data; boundary=\(boundary)"
        )
    }

    // MARK: - 底层

    /// 执行一次原始请求并把响应解析为 JSON 对象（供 token 获取等无 token 接口复用）。
    static func perform(_ request: URLRequest) async throws -> [String: Any] {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw WeChatAPIError.transport(error)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw WeChatAPIError.httpStatus(http.statusCode)
        }
        guard let object = try? JSONSerialization.jsonObject(with: data),
              let payload = object as? [String: Any] else {
            throw WeChatAPIError.malformedResponse
        }
        return payload
    }

    private static func sendWithToken(
        path: String,
        method: String,
        queryItems: [URLQueryItem],
        body: Data?,
        contentType: String?
    ) async throws -> [String: Any] {
        var attempt = 0
        while true {
            let token = try await TokenManager.shared.token(forceRefresh: attempt > 0)

            guard var components = URLComponents(string: host + path) else {
                throw WeChatAPIError.invalidURL
            }
            components.queryItems = queryItems + [URLQueryItem(name: "access_token", value: token)]
            guard let url = components.url else { throw WeChatAPIError.invalidURL }

            var request = URLRequest(url: url)
            request.httpMethod = method
            request.timeoutInterval = 30
            request.httpBody = body
            if let contentType {
                request.setValue(contentType, forHTTPHeaderField: "Content-Type")
            }

            let payload = try await perform(request)

            if let code = payload["errcode"] as? Int, code != 0 {
                // token 失效：刷新后重试一次
                if attempt == 0, WeChatErrorCode.tokenExpiredCodes.contains(code) {
                    await TokenManager.shared.invalidate()
                    attempt += 1
                    continue
                }
                throw WeChatAPIError.api(code: code, message: (payload["errmsg"] as? String) ?? "")
            }
            return payload
        }
    }

    private static func multipartBody(
        boundary: String,
        fileField: String,
        filename: String,
        mimeType: String,
        fileData: Data,
        extraFields: [String: String]
    ) -> Data {
        var data = Data()
        func append(_ string: String) {
            data.append(Data(string.utf8))
        }

        for (key, value) in extraFields.sorted(by: { $0.key < $1.key }) {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n")
            append("\(value)\r\n")
        }

        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"\(fileField)\"; filename=\"\(filename)\"\r\n")
        append("Content-Type: \(mimeType)\r\n\r\n")
        data.append(fileData)
        append("\r\n--\(boundary)--\r\n")

        return data
    }
}

// MARK: - JSON 取值辅助

extension Dictionary where Key == String, Value == Any {
    /// JSONSerialization 的数值统一为 NSNumber，这里做安全取值。
    func intValue(_ key: String) -> Int? {
        if let value = self[key] as? Int { return value }
        if let value = self[key] as? Double { return Int(value) }
        if let value = self[key] as? String { return Int(value) }
        return nil
    }

    func doubleValue(_ key: String) -> Double? {
        if let value = self[key] as? Double { return value }
        if let value = self[key] as? Int { return Double(value) }
        if let value = self[key] as? String { return Double(value) }
        return nil
    }

    func stringValue(_ key: String) -> String? {
        self[key] as? String
    }

    func arrayValue(_ key: String) -> [[String: Any]]? {
        self[key] as? [[String: Any]]
    }
}
