import SwiftUI

/// 根视图：五个功能页 + 全局提示条。
struct RootView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(spacing: 0) {
            TabView {
                AccountView()
                    .tabItem { Label("账号", systemImage: "person.crop.circle") }
                ComposerView()
                    .tabItem { Label("编辑", systemImage: "square.and.pencil") }
                MediaView()
                    .tabItem { Label("素材", systemImage: "photo.on.rectangle") }
                DraftListView()
                    .tabItem { Label("草稿", systemImage: "tray.full") }
                PublishView()
                    .tabItem { Label("发布", systemImage: "paperplane") }
            }
            .padding(.top, 8)

            NoticeBar()
        }
    }
}

/// 全局提示条（成功 / 失败 + 忙碌指示）。
struct NoticeBar: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        HStack(spacing: 10) {
            if state.isBusy {
                ProgressView()
                    .controlSize(.small)
            }
            Text(state.notice.isEmpty ? "就绪" : state.notice)
                .font(.callout)
                .foregroundStyle(state.noticeIsError ? Color.red : Color.secondary)
                .lineLimit(3)
                .textSelection(.enabled)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(.bar)
    }
}
