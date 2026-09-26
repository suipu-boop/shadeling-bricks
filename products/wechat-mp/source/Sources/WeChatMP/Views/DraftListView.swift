import SwiftUI
import BrickUIKit

/// 草稿页：列表 / 刷新 / 删除 / 设为发布目标。
struct DraftListView: View {
    @EnvironmentObject private var state: AppState
    @State private var pendingDeletion: DraftSummary?

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Button("刷新草稿列表") {
                    Task { await state.refreshDrafts() }
                }
                .disabled(state.isBusy || !state.account.isComplete)

                Text("单次最多返回 20 条；删除操作不可撤销")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer()

                Text("共 \(state.drafts.count) 条")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            if state.drafts.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "tray")
                        .font(.system(size: 36))
                        .foregroundStyle(.tertiary)
                    Text("暂无草稿。可在「编辑」页撰写内容并保存到草稿箱。")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(state.drafts) { draft in
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(draft.title)
                                    .font(.headline)
                                if !draft.digest.isEmpty {
                                    Text(draft.digest)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                                Text("media_id：\(draft.mediaID)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .textSelection(.enabled)
                            }

                            Spacer()

                            Text(draft.displayTime)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Button("设为发布目标") {
                                state.selectedDraftMediaID = draft.mediaID
                                state.notice = "已选择草稿：\(draft.title)"
                                state.noticeIsError = false
                            }

                            Button("删除", role: .destructive) {
                                pendingDeletion = draft
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        // 弹层契约（规格 v0.1 §1.4）：破坏性确认必须走 .brickConfirm（底层 .confirmationDialog），
        // 禁止业务直接调 .alert。
        .brickConfirm(
            title: "确认删除草稿？",
            message: "草稿「\(pendingDeletion?.title ?? "")」删除后不可恢复，需要重新创建。",
            confirmLabel: "删除",
            destructive: true,
            isPresented: Binding(
                get: { pendingDeletion != nil },
                set: { if !$0 { pendingDeletion = nil } }
            )
        ) {
            if let draft = pendingDeletion {
                Task { await state.deleteDraft(mediaID: draft.mediaID) }
            }
            pendingDeletion = nil
        }
    }
}
