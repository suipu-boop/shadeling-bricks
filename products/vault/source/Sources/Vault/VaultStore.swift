import Foundation
import SQLite3

/// sqlite3_bind_text 专用析构标记（SQLITE_TRANSIENT 的 Swift 等价）。
private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

// MARK: - Vault 存储引擎（纯 Swift，读写底座同源库）
// 兼容约束（与 runtime/vault_store.py 严格对齐，勿擅自改列/结构）：
// - 库文件：SHADELING_HOME/vault/vault.db（SHADELING_HOME 缺省时回退
//   ~/Library/Application Support/Shadeling/vault，再回退 ~/.shadeling/vault）
// - 表 assets(id TEXT PK, type TEXT, title TEXT, created_at REAL, updated_at REAL, payload TEXT)
// - payload JSON: { fields:{}, enc:{敏感字段: openssl base64}, file_ref, source, ai:{...} }
// - 敏感字段加密：openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:<key> -base64
//   key 优先 macOS 钥匙串(shadeling-vault/vault-key)，回退 vault/.vault_key（0600）

enum VaultPaths {
    /// 与 python vault_store._resolve_vault_dir() 推导一致。
    static var vaultDir: URL {
        if let home = ProcessInfo.processInfo.environment["SHADELING_HOME"],
           !home.isEmpty {
            return URL(fileURLWithPath: home).appendingPathComponent("vault")
        }
        let newHome = FileManager.default.urls(for: .applicationSupportDirectory,
                                               in: .userDomainMask).first!
            .appendingPathComponent("Shadeling").appendingPathComponent("vault")
        if FileManager.default.fileExists(atPath: newHome.path) { return newHome }
        let legacy = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent(".shadeling").appendingPathComponent("vault")
        if FileManager.default.fileExists(atPath: legacy.path) { return legacy }
        return newHome
    }
}

enum VaultError: LocalizedError {
    case dbOpen(String)
    case dbExec(String)
    case crypto(String)
    case type(String)
    var errorDescription: String? {
        switch self {
        case .dbOpen(let m): return "无法打开数据库：\(m)"
        case .dbExec(let m): return "数据库操作失败：\(m)"
        case .crypto(let m): return "加密/解密失败：\(m)"
        case .type(let m): return m
        }
    }
}

/// 轻量 SQLite 连接封装（仅本 app 自用，绑定参数防注入）。
final class VaultDB {
    private var db: OpaquePointer?
    let url: URL

    init(url: URL) throws {
        self.url = url
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        var handle: OpaquePointer?
        let rc = sqlite3_open_v2(url.path, &handle,
                                 SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
                                 nil)
        guard rc == SQLITE_OK, let handle else {
            let msg = handle.map { String(cString: sqlite3_errmsg($0)) } ?? "rc=\(rc)"
            throw VaultError.dbOpen(msg)
        }
        db = handle
        try exec("""
        CREATE TABLE IF NOT EXISTS assets (
            id          TEXT PRIMARY KEY,
            type        TEXT NOT NULL,
            title       TEXT NOT NULL,
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL,
            payload     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
        """)
    }

    deinit { if let db { sqlite3_close(db) } }

    func exec(_ sql: String) throws {
        var err: UnsafeMutablePointer<CChar>?
        let rc = sqlite3_exec(db, sql, nil, nil, &err)
        guard rc == SQLITE_OK else {
            let msg = err.map { String(cString: $0) } ?? "rc=\(rc)"
            sqlite3_free(err)
            throw VaultError.dbExec(msg)
        }
    }

    /// 执行带绑定的查询，逐行回调。
    func query(_ sql: String, _ binds: [Any] = [], row: (OpaquePointer) -> Void) throws {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else {
            throw VaultError.dbExec(String(cString: sqlite3_errmsg(db)))
        }
        defer { sqlite3_finalize(stmt) }
        for (i, b) in binds.enumerated() {
            let idx = Int32(i + 1)
            switch b {
            case let s as String: sqlite3_bind_text(stmt, idx, s, -1, sqliteTransient)
            case let d as Double: sqlite3_bind_double(stmt, idx, d)
            case let i as Int: sqlite3_bind_int64(stmt, idx, Int64(i))
            default: break
            }
        }
        while true {
            let rc = sqlite3_step(stmt)
            if rc == SQLITE_ROW {
                row(stmt)
            } else if rc == SQLITE_DONE {
                break
            } else {
                throw VaultError.dbExec(String(cString: sqlite3_errmsg(db)))
            }
        }
    }

    func queryScalarString(_ sql: String, _ binds: [Any] = []) throws -> String? {
        var result: String?
        try query(sql, binds) { stmt in
            if let c = sqlite3_column_text(stmt, 0) { result = String(cString: c) }
        }
        return result
    }
}

// MARK: - 加密（子进程 openssl，与底座命令逐参一致）

enum VaultCrypto {
    static let keychainService = "shadeling-vault"
    static let keychainAccount = "vault-key"

    static func loadOrCreateKey(vaultDir: URL) throws -> String {
        // 1) 钥匙串
        if let k = keychainFind() { return k }
        // 2) keyfile
        let kf = vaultDir.appendingPathComponent(".vault_key")
        if let s = try? String(contentsOf: kf, encoding: .utf8), !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return s.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // 3) 生成并存（与 python _gen_key/_store_key 一致）
        let key = run("/usr/bin/openssl", ["rand", "-hex", "32"]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard key.count == 64 else { throw VaultError.crypto("openssl rand 生成密钥失败") }
        _ = run("/usr/bin/security", ["add-generic-password", "-s", keychainService,
                                      "-a", keychainAccount, "-w", key, "-U"])
        try FileManager.default.createDirectory(at: vaultDir, withIntermediateDirectories: true)
        try key.write(to: kf, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: kf.path)
        return key
    }

    private static func keychainFind() -> String? {
        let out = run("/usr/bin/security",
                      ["find-generic-password", "-s", keychainService, "-a", keychainAccount, "-w"])
        let s = out.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? nil : s
    }

    static func encrypt(_ plain: String, key: String) throws -> String {
        let out = runWithInput("/usr/bin/openssl",
                               ["enc", "-aes-256-cbc", "-salt", "-pbkdf2",
                                "-pass", "pass:\(key)", "-base64"],
                               input: plain)
        guard !out.isEmpty else { throw VaultError.crypto("openssl enc 无输出") }
        return out.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func decrypt(_ blob: String, key: String) throws -> String {
        let out = runWithInput("/usr/bin/openssl",
                               ["enc", "-d", "-aes-256-cbc", "-pbkdf2",
                                "-pass", "pass:\(key)", "-base64"],
                               input: blob)
        return out
    }

    // MARK: 进程辅助
    private static func run(_ path: String, _ args: [String]) -> String {
        runWithInput(path, args, input: nil)
    }

    private static func runWithInput(_ path: String, _ args: [String], input: String?) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: path)
        p.arguments = args
        let out = Pipe(); let err = Pipe()
        p.standardOutput = out; p.standardError = err
        if let input {
            let inp = Pipe()
            p.standardInput = inp
            do {
                try p.run()
                try inp.fileHandleForWriting.write(contentsOf: Data(input.utf8))
                try inp.fileHandleForWriting.close()
            } catch { return "" }
        } else {
            do { try p.run() } catch { return "" }
        }
        let od = out.fileHandleForReading.readDataToEndOfFile()
        return String(data: od, encoding: .utf8) ?? ""
    }
}

// MARK: - 脱敏

func maskNumber(_ s: String) -> String {
    let s = s.trimmingCharacters(in: .whitespacesAndNewlines)
    if s.count <= 8 {
        return String(s.prefix(1)) + String(repeating: "*", count: max(0, s.count - 1))
    }
    return String(s.prefix(4)) + String(repeating: "*", count: s.count - 8) + String(s.suffix(4))
}

// MARK: - VaultStore 主类

final class VaultStore: ObservableObject {
    static let assetTypes = ["document", "image", "webpage", "skill_snapshot", "note"]

    @Published private(set) var items: [VaultAsset] = []
    @Published private(set) var lastError: String?

    let vaultDir: URL
    private let db: VaultDB
    private var cryptoKey: String?

    init(vaultDir: URL = VaultPaths.vaultDir) throws {
        self.vaultDir = vaultDir
        self.db = try VaultDB(url: vaultDir.appendingPathComponent("vault.db"))
    }

    // MARK: - 查询

    func reload(type: String? = nil, q: String? = nil) {
        do {
            items = try fetch(type: type, q: q)
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    func fetch(type: String?, q: String?) throws -> [VaultAsset] {
        var sql = "SELECT id,type,title,created_at,updated_at,payload FROM assets"
        var wheres: [String] = []; var binds: [Any] = []
        if let type { wheres.append("type=?"); binds.append(type) }
        if let q, !q.isEmpty { wheres.append("(title LIKE ? OR payload LIKE ?)"); binds += ["%\(q)%", "%\(q)%"] }
        if !wheres.isEmpty { sql += " WHERE " + wheres.joined(separator: " AND ") }
        sql += " ORDER BY updated_at DESC LIMIT 500"
        var out: [VaultAsset] = []
        try db.query(sql, binds) { stmt in
            let d = rowToAsset(stmt, includeSensitive: false)
            if let a = d { out.append(a) }
        }
        return out
    }

    func asset(id: String, includeSensitive: Bool) throws -> VaultAsset? {
        var found: VaultAsset?
        try db.query("SELECT id,type,title,created_at,updated_at,payload FROM assets WHERE id=?",
                     [id]) { stmt in
            if let a = rowToAsset(stmt, includeSensitive: includeSensitive) { found = a }
        }
        return found
    }

    private func rowToAsset(_ stmt: OpaquePointer, includeSensitive: Bool) -> VaultAsset? {
        guard let cId = sqlite3_column_text(stmt, 0),
              let cType = sqlite3_column_text(stmt, 1),
              let cTitle = sqlite3_column_text(stmt, 2),
              let cPayload = sqlite3_column_text(stmt, 5) else { return nil }
        let id = String(cString: cId)
        let type = String(cString: cType)
        let title = String(cString: cTitle)
        let created = sqlite3_column_double(stmt, 3)
        let updated = sqlite3_column_double(stmt, 4)
        guard let p = (try? JSONSerialization.jsonObject(with: Data(String(cString: cPayload).utf8)))
                as? [String: Any] else {
            return VaultAsset(id: id, type: type, title: title, createdAt: created, updatedAt: updated)
        }
        let fields = p["fields"] as? [String: Any] ?? [:]
        let enc = p["enc"] as? [String: String] ?? [:]
        var dict: [String: Any] = [
            "id": id, "type": type, "title": title,
            "created_at": created, "updated_at": updated,
            "file_ref": p["file_ref"], "has_sensitive": !enc.isEmpty,
            "source": p["source"] ?? ""
        ]
        for (k, v) in fields { dict[k] = v }
        let ai = p["ai"] as? [String: Any] ?? [:]
        dict["ai_summary"] = ai["summary"] ?? ""
        dict["ai_tags"] = ai["ai_tags"] ?? []
        dict["ai_key_points"] = ai["key_points"] ?? []
        if includeSensitive && !enc.isEmpty {
            for (k, blob) in enc {
                dict[k] = try? decryptValue(blob) ?? "***解密失败***"
            }
        }
        return VaultAsset(from: dict)
    }

    /// 解密单个密文（详情解锁用）。失败返回 nil 由调用方兜底显示失败文案。
    func decryptValue(_ blob: String) throws -> String? {
        let key = try key()
        return try VaultCrypto.decrypt(blob, key: key)
    }

    // MARK: - 增（手动录入 / AI 沉淀共用）

    /// type: document/note/webpage；fields: 非敏感；sensitive: {字段: 明文} 会被加密进 enc；
    /// source: "ai" 表示 AI 自主沉淀渠道写入（可选，默认手动）。
    @discardableResult
    func add(type: String, title: String? = nil,
             fields: [String: String],
             sensitive: [String: String] = [:],
             source: String? = nil) throws -> VaultAsset {
        guard Self.assetTypes.contains(type) else { throw VaultError.type("未知资产类型：\(type)") }
        let now = Date().timeIntervalSince1970
        let aid = UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12).lowercased()
        let key = try key()
        var enc: [String: String] = [:]
        var outFields = fields
        // document.number_full 加密 + 脱敏（与底座语义一致）
        if type == "document", let num = outFields["number_full"], !num.isEmpty {
            outFields.removeValue(forKey: "number_full")
            enc["number_full"] = try VaultCrypto.encrypt(num, key: key)
            outFields["number_masked"] = maskNumber(num)
        }
        // note/account 的口令类敏感字段
        for (k, v) in sensitive where !v.isEmpty {
            enc[k] = try VaultCrypto.encrypt(v, key: key)
        }
        var payload: [String: Any] = ["fields": outFields, "enc": enc, "file_ref": NSNull()]
        if let source, !source.isEmpty { payload["source"] = source }
        let resolvedTitle = (title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let finalTitle = resolvedTitle.isEmpty ? defaultTitle(type, outFields) : resolvedTitle
        let payloadData = try JSONSerialization.data(withJSONObject: payload, options: [])
        let payloadStr = String(data: payloadData, encoding: .utf8) ?? "{}"
        try db.exec("""
        INSERT INTO assets (id,type,title,created_at,updated_at,payload) VALUES
        ('\(aid)','\(type)','\(sqlEscape(finalTitle))',\(now),\(now),'\(sqlEscape(payloadStr))')
        """)
        let asset = VaultAsset(id: aid, type: type, title: finalTitle,
                               createdAt: now, updatedAt: now,
                               hasSensitive: !enc.isEmpty,
                               source: source,
                               aiTags: fields["text"].map { _ in [] } ?? [])
        return asset
    }

    /// 详情解锁：返回该资产 enc 段全部明文（{字段名: 明文}）。无 enc 返回空字典。
    func plainFields(id: String) throws -> [String: String] {
        guard let payload = try db.queryScalarString("SELECT payload FROM assets WHERE id=?", [id]),
              let p = (try? JSONSerialization.jsonObject(with: Data(payload.utf8))) as? [String: Any],
              let enc = p["enc"] as? [String: String], !enc.isEmpty else { return [:] }
        let key = try key()
        var out: [String: String] = [:]
        for (k, blob) in enc {
            do {
                out[k] = try VaultCrypto.decrypt(blob, key: key)
            } catch {
                out[k] = "***解密失败***"
            }
        }
        return out
    }

    // MARK: - 删

    func delete(id: String) {
        let fm = FileManager.default
        let fd = vaultDir.appendingPathComponent(id)
        if fm.fileExists(atPath: fd.path) { try? fm.removeItem(at: fd) }
        try? db.exec("DELETE FROM assets WHERE id='\(sqlEscape(id))'")
    }

    // MARK: - 私有

    private func key() throws -> String {
        if let cryptoKey { return cryptoKey }
        let k = try VaultCrypto.loadOrCreateKey(vaultDir: vaultDir)
        cryptoKey = k
        return k
    }

    private func defaultTitle(_ type: String, _ fields: [String: String]) -> String {
        switch type {
        case "document":
            return fields["doc_type"] ?? "证件"
        case "webpage":
            return fields["title"] ?? fields["url"] ?? "收藏"
        case "note":
            if let text = fields["text"], !text.isEmpty {
                return String(text.prefix(24))
            }
            return fields["account_name"] ?? "笔记"
        default: return "资产"
        }
    }

    private func sqlEscape(_ s: String) -> String {
        s.replacingOccurrences(of: "'", with: "''")
    }
}
