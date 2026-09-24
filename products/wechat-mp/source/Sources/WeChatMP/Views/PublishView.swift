import SwiftUI

/// 发布页：按账号实际权限决定是否开放发布入口。
///
/// 发布入口仅在探测到 freepublish 权限时显示；否则隐藏并给出原因说明。
struct PublishView: View {
    @EnvironmentObject private var state: AppState
    @State private var statusText: String = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                permissionCard

                if state.publishPermission.isGranted {
                    publishCard
                }

                explainCard

                Spacer(minLength: 0)
            }
            .padding(20)
            .frame(maxWidth: 760, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    // MARK: - 权限卡

    private var permissionCard: some View {
        GroupBox("发布权限") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    switch state.publishPermission {
                    case .unknown:
                        Label("尚未探测", systemImage: "questionmark.circle")
                            .foregroundStyle(.secondary)
                    case .probing:
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("正在探测…")
                        }
                    case .granted:
                        Label("可用（freepublish）", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                    case .denied(let reason):
                        Label("不可用", systemImage: "xmark.seal")
                            .foregroundStyle(.orange)
                            .help(reason)
                    }

                    Spacer()

                    Button("重新探测") {
                        Task { await state.refreshPublishPermission() }
                    }
                    .disabled(state.isBusy || !state.account.isComplete)
                }

                if case .denied(let reason) = state.publishPermission {
                    Text(reason)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(8)
        }
    }

    // MARK: - 发布卡（仅权限可用时展示）

    private var publishCard: some View {
        GroupBox("提交发布") {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Text("目标草稿")
                        .frame(width: 80, alignment: .trailing)
                    Picker("", selection: $state.selectedDraftMediaID) {
                        Text("未选择").tag("")
                        ForEach(state.drafts) { draft in
                            Text("\(draft.title) · \(draft.mediaID.prefix(10))…")
                                .tag(draft.mediaID)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 360)

                    Button("刷新列表") {
                        Task { await state.refreshDrafts() }
                    }
                }

                HStack(spacing: 12) {
                    Spacer().frame(width: 80)
                    Button("提交发布") {
                        Task {
                            if let result = await state.publish(mediaID: state.selectedDraftMediaID) {
                                state.lastPublishID = result.publishID
                                statusText = ""
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(state.isBusy || state.selectedDraftMediaID.isEmpty)

                    Button("查询发布状态") {
                        Task {
                            guard !state.lastPublishID.isEmpty else {
                                statusText = "请先提交发布，或手动填入 publish_id。"
                                return
                            }
                            do {
                                statusText = try await PublishService.status(publishID: state.lastPublishID)
                            } catch {
                                statusText = "查询失败：\(error.localizedDescription)"
                            }
                        }
                    }
                    .disabled(state.isBusy || state.lastPublishID.isEmpty)
                }

                HStack(spacing: 12) {
                    Text("publish_id")
                        .frame(width: 80, alignment: .trailing)
                    TextField("提交发布后自动填入", text: $state.lastPublishID)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 360)
                }

                if !statusText.isEmpty {
                    Text("发布状态：\(statusText)")
                        .font(.callout)
                        .textSelection(.enabled)
                }
            }
            .padding(8)
        }
    }

    // MARK: - 说明卡

    private var explainCard: some View {
        GroupBox("为什么看不到发布按钮？") {
            VStack(alignment: .leading, spacing: 8) {
                line("发布接口 freepublish 需要账号具备相应权限：服务号、已认证的企业订阅号可用；")
                line("个人主体账号、企业未认证账号自 2025 年 7 月起已被微信回收该权限。")
                line("这类账号仍可通过本积木创建、管理草稿，最终发布请在微信公众平台后台手动完成。")
                line("权限探测通过只读接口 freepublish/batchget 完成，不会产生任何发布行为。")
            }
            .font(.callout)
            .foregroundStyle(.secondary)
            .padding(8)
        }
    }

    private func line(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
    }
}
