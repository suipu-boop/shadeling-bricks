import Foundation

/// 公众号账号配置。
///
/// 注意：AppSecret **不写入源码、不写入 manifest、不进 git**，
/// 仅由用户在应用界面填写后落盘到本机私有目录。
struct AccountConfig: Codable, Equatable {
    var appID: String = ""
    var appSecret: String = ""

    var isComplete: Bool {
        !appID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !appSecret.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var normalized: AccountConfig {
        AccountConfig(
            appID: appID.trimmingCharacters(in: .whitespacesAndNewlines),
            appSecret: appSecret.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }
}

/// 账号凭据本地持久化。
///
/// 存储位置：`~/Library/Application Support/com.shadeling.brick.wechat-mp/account.json`
/// 文件权限：`0600`（仅当前用户可读写）。该目录与源码 / git 仓库完全隔离。
final class CredentialStore {
    static let shared = CredentialStore()

    /// 应用私有目录名（与积木 id 一致，便于卸载时整体清理）
    static let bundleDirectoryName = "com.shadeling.brick.wechat-mp"

    private let fileManager = FileManager.default
    private let directoryURL: URL
    private let fileURL: URL

    private init() {
        let base = fileManager
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first
            ?? URL(fileURLWithPath: NSHomeDirectory())
                .appendingPathComponent("Library/Application Support", isDirectory: true)
        directoryURL = base.appendingPathComponent(Self.bundleDirectoryName, isDirectory: true)
        fileURL = directoryURL.appendingPathComponent("account.json")
    }

    /// 供界面展示的存储路径
    var storageDirectory: URL { directoryURL }

    func load() -> AccountConfig {
        guard let data = try? Data(contentsOf: fileURL),
              let config = try? JSONDecoder().decode(AccountConfig.self, from: data) else {
            return AccountConfig()
        }
        return config
    }

    func save(_ config: AccountConfig) throws {
        try fileManager.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(config.normalized)
        try data.write(to: fileURL, options: [.atomic])
        // 收紧权限：仅当前用户可读写
        try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
    }

    func clear() throws {
        guard fileManager.fileExists(atPath: fileURL.path) else { return }
        try fileManager.removeItem(at: fileURL)
    }
}
