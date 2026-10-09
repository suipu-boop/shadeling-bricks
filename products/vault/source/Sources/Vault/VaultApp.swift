// [已退役 · 2026-10-09 · 主契约 §6.4 / §7.6]
// 本目录属 v1 legacy 独立 .app 形态，随 Phase E 退役：BrickUIKit.BrickScene（含 BrickLifecycleView）
// 已物理删除，本源码不再参与出包（v2 形态走 ui/*.json + logic/*），保留仅作历史参考与数据取证；
// 请勿据此重新构建 v1 .app。

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
