import SwiftUI
import BrickUIKit

/// 应用入口。
///
/// 本积木以独立应用形态运行（独立窗口），由 Shadeling 底座管理启动 / 卸载。
/// 打包为 `WeChatMP.app` 后即可正常激活窗口；直接 `swift run` 时窗口可能不在前台，
/// 请用 `open dist/WeChatMP.app` 方式启动（详见 README）。
@main
struct WeChatMPApp: App {
    @StateObject private var state = AppState()

    /// 窗口契约（规格 v0.1 §1.3）：hiddenTitleBar / 默认 980×680 / 最小 760×520 /
    /// 单 WindowGroup 且禁用 Cmd+N / 关最后一个窗口即退出进程 —— 全部由 BrickScene 承载
    ///（迁移前为 1120×720 无 defaultSize + 系统标题栏）。
    var body: some Scene {
        BrickScene(title: "微信公众号") {
            RootView()
                .environmentObject(state)
        }
        .commands {
            // 业务专属快捷键（规格 v0.1 §1.5 属"必须自由"）：Cmd+R 刷新草稿列表。
            CommandGroup(after: .toolbar) {
                Button("刷新草稿列表") {
                    Task { await state.refreshDrafts() }
                }
                .keyboardShortcut("r", modifiers: [.command])
            }
        }
    }
}
