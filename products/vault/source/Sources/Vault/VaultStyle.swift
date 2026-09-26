import SwiftUI
import BrickUIKit

// MARK: - vault 产品样式（令牌统一来自 BrickUIKit）
//
// 规格 v0.1 §1.2 / §1.5：颜色 / 圆角 / 间距令牌与按钮语义统一进 BrickUIKit，
// 本文件只保留包内未覆盖的「产品自有玻璃壳」样式（渐变背景上的玻璃填充 / 胶囊按钮 /
// 资产类型配色），其余一律引用 `Design.*`（BrickUIKit L1）。
//
// 注意：此处**不得**再定义名为 `Design` 的类型——与包内令牌重名会静默遮蔽
//（规格 §3 Phase 0 风险点：重复定义会用了本地副本，迁移形同虚设）。

/// 玻璃壳填充 / 描边（BrickUIKit L1 暂无「渐变背景上的卡片玻璃」令牌，暂由 vault 自持；
/// 待包内补齐同类令牌后再回收）。
enum VaultGlass {
    static var fill: Color { Color(red: 0.16, green: 0.12, blue: 0.36).opacity(0.30) }
    static var fillStrong: Color { Color(red: 0.16, green: 0.12, blue: 0.36).opacity(0.44) }
    static var stroke: Color { Color.white.opacity(0.14) }
    static var strokeHover: Color { Color.white.opacity(0.26) }
}

/// 玻璃胶囊按钮（prominent = 主操作）
struct GlassButtonStyle: ButtonStyle {
    var prominent: Bool = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: prominent ? .semibold : .medium))
            .padding(.horizontal, prominent ? 18 : 12)
            .padding(.vertical, 7)
            .background(
                Capsule()
                    .fill(prominent ? Design.ColorPalette.accent : Color.white.opacity(0.16))
            )
            .foregroundStyle(.white)
            .overlay(Capsule().stroke(Color.white.opacity(prominent ? 0.25 : 0.16), lineWidth: 1))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension View {
    func glassButton(prominent: Bool = false) -> some View {
        buttonStyle(GlassButtonStyle(prominent: prominent))
    }
}

/// 资产类型配色（与底座 VaultView 一致）
func typeColor(_ type: String) -> Color {
    switch type {
    case "document": return Color(red: 0.46, green: 0.70, blue: 1.0)
    case "image": return Color(red: 0.36, green: 0.80, blue: 0.58)
    case "webpage": return Color(red: 1.0, green: 0.70, blue: 0.36)
    case "skill_snapshot": return Color(red: 0.75, green: 0.55, blue: 1.0)
    case "note": return Color(red: 0.72, green: 0.74, blue: 0.80)
    default: return .gray
    }
}

func typeLabel(_ type: String) -> String {
    switch type {
    case "document": return "证件"
    case "image": return "图片"
    case "webpage": return "收藏"
    case "skill_snapshot": return "技能"
    case "note": return "笔记"
    default: return type
    }
}
