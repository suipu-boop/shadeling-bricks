import Foundation
import SwiftUI

/// 全局应用状态：账号 / 编辑 / 素材 / 草稿 / 发布权限。
@MainActor
final class AppState: ObservableObject {

    // MARK: - 账号

    @Published var account: AccountConfig = CredentialStore.shared.load()
    @Published var accountReport: String = ""
    @Published var isTestingAccount = false
    @Published var isSavingAccount = false

    // MARK: - 内容编辑

    @Published var markdown: String = AppState.sampleMarkdown
    @Published var themeID: String = WeChatTheme.default.id
    @Published var payload = DraftPayload()

    // MARK: - 素材 / 草稿 / 发布

    @Published var mediaAssets: [MediaAsset] = MediaLibrary.load()
    @Published var drafts: [DraftSummary] = []
    @Published var publishPermission: PublishPermission = .unknown
    @Published var selectedDraftMediaID: String = ""
    @Published var lastPublishID: String = ""

    // MARK: - 通用提示

    @Published var isBusy = false
    @Published var notice: String = ""
    @Published var noticeIsError = false

    var theme: WeChatTheme {
        WeChatTheme.all.first { $0.id == themeID } ?? WeChatTheme.default
    }

    /// 当前 Markdown 渲染出的微信兼容 HTML
    var renderedHTML: String {
        MarkdownRenderer.render(markdown: markdown, theme: theme)
    }

    var storagePath: String {
        CredentialStore.shared.storageDirectory.path
    }

    // MARK: - 账号

    func saveAccount() {
        isSavingAccount = true
        defer { isSavingAccount = false }
        do {
            try CredentialStore.shared.save(account)
            account = CredentialStore.shared.load()
            notice = "凭据已保存到本机私有目录（权限 0600）：\(storagePath)"
            noticeIsError = false
            // 凭据变更后清空 token 缓存
            Task { await TokenManager.shared.invalidate() }
        } catch {
            notice = "保存失败：\(error.localizedDescription)"
            noticeIsError = true
        }
    }

    /// 测试连接：分步校验 凭据 → 接口连通（IP 白名单） → 发布权限
    func testConnection() async {
        isTestingAccount = true
        defer { isTestingAccount = false }

        var report: [String] = []
        publishPermission = .unknown

        do {
            _ = try await TokenManager.shared.token(forceRefresh: true)
            report.append("① 凭据校验：通过（access_token 获取成功）")
        } catch {
            report.append("① 凭据校验：失败 — \(error.localizedDescription)")
            accountReport = report.joined(separator: "\n")
            return
        }

        do {
            let total = try await DraftService.count()
            report.append("② 接口连通：通过（IP 白名单已生效），当前草稿总数 \(total)")
        } catch {
            report.append("② 接口连通：失败 — \(error.localizedDescription)")
        }

        let permission = await PublishService.probePermission()
        publishPermission = permission
        switch permission {
        case .granted:
            report.append("③ 发布权限：可用（freepublish）")
        case .denied(let reason):
            report.append("③ 发布权限：不可用 — \(reason)")
        default:
            report.append("③ 发布权限：未探测")
        }

        accountReport = report.joined(separator: "\n")
    }

    // MARK: - 素材

    func uploadImage(at url: URL) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let asset = try await MediaService.uploadImage(fileURL: url)
            mediaAssets = MediaLibrary.appending(asset, to: mediaAssets)
            MediaLibrary.save(mediaAssets)
            if payload.thumbMediaID.isEmpty {
                payload.thumbMediaID = asset.mediaID
            }
            notice = "素材上传成功：media_id = \(asset.mediaID)"
            noticeIsError = false
        } catch {
            notice = "素材上传失败：\(error.localizedDescription)"
            noticeIsError = true
        }
    }

    // MARK: - 草稿

    func createDraft() async -> String? {
        isBusy = true
        defer { isBusy = false }
        payload.contentHTML = renderedHTML
        do {
            let mediaID = try await DraftService.create(payload)
            notice = "草稿已创建：media_id = \(mediaID)"
            noticeIsError = false
            await refreshDrafts()
            return mediaID
        } catch {
            notice = "创建草稿失败：\(error.localizedDescription)"
            noticeIsError = true
            return nil
        }
    }

    func refreshDrafts() async {
        isBusy = true
        defer { isBusy = false }
        do {
            drafts = try await DraftService.list()
            notice = "已加载 \(drafts.count) 条草稿"
            noticeIsError = false
        } catch {
            notice = "草稿列表加载失败：\(error.localizedDescription)"
            noticeIsError = true
        }
    }

    func deleteDraft(mediaID: String) async {
        isBusy = true
        defer { isBusy = false }
        do {
            try await DraftService.delete(mediaID: mediaID)
            drafts.removeAll { $0.mediaID == mediaID }
            notice = "草稿已删除：\(mediaID)"
            noticeIsError = false
        } catch {
            notice = "删除草稿失败：\(error.localizedDescription)"
            noticeIsError = true
        }
    }

    // MARK: - 发布

    func refreshPublishPermission() async {
        publishPermission = .probing
        publishPermission = await PublishService.probePermission()
    }

    func publish(mediaID: String) async -> PublishResult? {
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await PublishService.publish(mediaID: mediaID)
            notice = "已提交发布：publish_id = \(result.publishID)"
            noticeIsError = false
            return result
        } catch let error as WeChatAPIError {
            if case .api(let code, let message) = error, WeChatErrorCode.isUnauthorized(code: code) {
                publishPermission = .denied(
                    reason: WeChatErrorCode.readableMessage(code: code, apiMessage: message)
                )
            }
            notice = "发布失败：\(error.localizedDescription)"
            noticeIsError = true
            return nil
        } catch {
            notice = "发布失败：\(error.localizedDescription)"
            noticeIsError = true
            return nil
        }
    }

    // MARK: - 示例内容

    static let sampleMarkdown = """
    # 文章标题

    在这里用 **Markdown** 撰写正文，右侧实时预览微信兼容排版效果。

    ## 小标题

    - 支持粗体、*斜体*、`行内代码`
    - 支持引用、列表、分割线
    - 支持 [链接](https://mp.weixin.qq.com) 与图片

    > 引用段落：所有样式均以内联方式输出，粘贴到微信编辑器不会丢样式。

    ---

    正文写完后，在下方填写标题、作者、摘要，并选择封面素材，即可保存到草稿箱。
    """
}
