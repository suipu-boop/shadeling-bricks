import SwiftUI
import BrickUIKit

@main
struct VaultApp: App {
    /// 窗口契约（规格 v0.1 §1.3）：hiddenTitleBar / 默认 980×680 / 最小 760×520 /
    /// 单 WindowGroup 且禁用 Cmd+N / 关最后一个窗口即退出进程 —— 全部由 BrickScene 承载。
    var body: some Scene {
        BrickScene(title: "本地资产中枢") {
            ContentView()
        }
    }
}
