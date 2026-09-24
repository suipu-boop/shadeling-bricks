import AppKit
import SwiftUI

/// 编辑页：Markdown 编辑 + 实时预览 + 草稿元信息 + 保存到草稿箱。
struct ComposerView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            HSplitView {
                editorPane
                    .frame(minWidth: 380, idealWidth: 520)
                previewPane
                    .frame(minWidth: 320, idealWidth: 420)
            }
            Divider()
            metaPane
        }
    }

    // MARK: - 顶部工具条

    private var toolbar: some View {
        HStack(spacing: 14) {
            Text("排版主题")
            Picker("", selection: $state.themeID) {
                ForEach(WeChatTheme.all) { theme in
                    Text(theme.name).tag(theme.id)
                }
            }
            .labelsHidden()
            .frame(width: 140)

            Text(state.theme.summary)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            Button("复制正文 HTML") {
                let pasteboard = NSPasteboard.general
                pasteboard.clearContents()
                pasteboard.setString(state.renderedHTML, forType: .string)
                state.notice = "正文 HTML 已复制到剪贴板，可直接粘贴到微信编辑器。"
                state.noticeIsError = false
            }

            Button("保存到草稿箱") {
                Task { _ = await state.createDraft() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(state.isBusy || !state.payload.isReady || !state.account.isComplete)
            .help(state.payload.isReady
                  ? "创建草稿"
                  : "还缺少：\(state.payload.missingItems.joined(separator: "、"))")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - 左：Markdown 编辑

    private var editorPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Markdown")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.top, 8)
            TextEditor(text: $state.markdown)
                .font(.system(.body, design: .monospaced))
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
        }
    }

    // MARK: - 右：预览

    private var previewPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("微信兼容预览")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.top, 8)
            HTMLPreviewView(html: state.renderedHTML)
        }
    }

    // MARK: - 底部：草稿元信息

    private var metaPane: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    Text("标题").frame(width: 70, alignment: .trailing)
                    TextField("必填，微信标题上限 64 字", text: $state.payload.title)
                        .textFieldStyle(.roundedBorder)
                }
                HStack(spacing: 12) {
                    Text("作者").frame(width: 70, alignment: .trailing)
                    TextField("选填", text: $state.payload.author)
                        .textFieldStyle(.roundedBorder)
                }
                HStack(spacing: 12) {
                    Text("摘要").frame(width: 70, alignment: .trailing)
                    TextField("选填，留空时微信自动截取正文开头", text: $state.payload.digest)
                        .textFieldStyle(.roundedBorder)
                }
                HStack(spacing: 12) {
                    Text("封面素材").frame(width: 70, alignment: .trailing)
                    Picker("", selection: $state.payload.thumbMediaID) {
                        Text("未选择（必填）").tag("")
                        ForEach(state.mediaAssets) { asset in
                            Text("\(asset.fileName) · \(asset.mediaID.prefix(12))…")
                                .tag(asset.mediaID)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 320)
                    if state.mediaAssets.isEmpty {
                        Text("请先在「素材」页上传封面图")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
                HStack(spacing: 12) {
                    Text("原文链接").frame(width: 70, alignment: .trailing)
                    TextField("选填，填写后「阅读原文」可跳转", text: $state.payload.contentSourceURL)
                        .textFieldStyle(.roundedBorder)
                }
                HStack(spacing: 18) {
                    Spacer().frame(width: 70)
                    Toggle("显示封面", isOn: $state.payload.showCoverPic)
                    Toggle("开启评论", isOn: $state.payload.needOpenComment)
                    Toggle("仅粉丝可评论", isOn: $state.payload.onlyFansCanComment)
                    Spacer()
                }
                if !state.payload.isReady {
                    Text("创建草稿还需补充：\(state.payload.missingItems.joined(separator: "、"))")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
            .padding(16)
        }
        .frame(height: 210)
    }
}
