import SwiftUI

/// 应用入口。
///
/// 本积木以独立应用形态运行（独立窗口），由 Shadeling 底座管理启动 / 卸载。
/// 打包为 `WeChatMP.app` 后即可正常激活窗口；直接 `swift run` 时窗口可能不在前台，
/// 请用 `open dist/WeChatMP.app` 方式启动（详见 README）。
@main
struct WeChatMPApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup("微信公众号") {
            RootView()
                .environmentObject(state)
                .frame(minWidth: 1120, minHeight: 720)
        }
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandGroup(after: .toolbar) {
                Button("刷新草稿列表") {
                    Task { await state.refreshDrafts() }
                }
                .keyboardShortcut("r", modifiers: [.command])
            }
        }
    }
}
