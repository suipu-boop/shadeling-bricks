import SwiftUI
import AppKit

// MARK: - 设计令牌（从 Shadeling 底座拷贝的最小玻璃风集合，保持窗口风格统一）

enum Design {
    static let radius: CGFloat = 10
    static let radiusSm: CGFloat = 6
    static let radiusLg: CGFloat = 16
    static let radiusBubble: CGFloat = 12

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 24
    }
    static let pad: CGFloat = Spacing.md

    private static func adaptive(light: NSColor, dark: NSColor) -> NSColor {
        AppKit.NSColor(name: nil, dynamicProvider: { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return isDark ? dark : light
        })
    }

    enum ColorPalette {
        static var surface: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.965, green: 0.969, blue: 0.976, alpha: 1),
                dark:  NSColor(red: 0.082, green: 0.090, blue: 0.110, alpha: 1)))
        }
        static var surfaceSecondary: Color {
            Color(Design.adaptive(
                light: NSColor(red: 1.0,   green: 1.0,   blue: 1.0,   alpha: 1),
                dark:  NSColor(red: 0.118, green: 0.129, blue: 0.157, alpha: 1)))
        }
        static var surfaceTertiary: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.933, green: 0.945, blue: 0.961, alpha: 1),
                dark:  NSColor(red: 0.149, green: 0.165, blue: 0.200, alpha: 1)))
        }
        static var accent: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.886, green: 0.259, blue: 0.565, alpha: 1),
                dark:  NSColor(red: 0.957, green: 0.373, blue: 0.702, alpha: 1)))
        }
        static var accentSoft: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.886, green: 0.259, blue: 0.565, alpha: 0.12),
                dark:  NSColor(red: 0.957, green: 0.373, blue: 0.702, alpha: 0.18)))
        }
        static var textSecondary: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.42, green: 0.45, blue: 0.52, alpha: 1),
                dark:  NSColor(red: 0.62, green: 0.65, blue: 0.72, alpha: 1)))
        }
        static var textPrimary: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.13, green: 0.15, blue: 0.19, alpha: 1),
                dark:  NSColor(red: 0.92, green: 0.93, blue: 0.96, alpha: 1)))
        }
        static var border: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.890, green: 0.906, blue: 0.933, alpha: 1),
                dark:  NSColor(red: 0.173, green: 0.192, blue: 0.231, alpha: 1)))
        }
        static var borderHover: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.788, green: 0.824, blue: 0.878, alpha: 1),
                dark:  NSColor(red: 0.227, green: 0.255, blue: 0.314, alpha: 1)))
        }
        static var success: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.129, green: 0.645, blue: 0.325, alpha: 1),
                dark:  NSColor(red: 0.188, green: 0.761, blue: 0.373, alpha: 1)))
        }
        static var warning: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.949, green: 0.639, blue: 0.059, alpha: 1),
                dark:  NSColor(red: 0.961, green: 0.710, blue: 0.267, alpha: 1)))
        }
        static var danger: Color {
            Color(Design.adaptive(
                light: NSColor(red: 0.898, green: 0.282, blue: 0.302, alpha: 1),
                dark:  NSColor(red: 1.000, green: 0.361, blue: 0.380, alpha: 1)))
        }
        static var info: Color { accent }
    }

    // MARK: 粉紫玻璃渐变（与 Shadeling 底座一致）
    static var appBackgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0.96, green: 0.16, blue: 0.61),
                Color(red: 0.70, green: 0.25, blue: 0.72),
                Color(red: 0.20, green: 0.14, blue: 0.39)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    /// 玻璃填充（深紫半透明，透出背景粉紫渐变）
    static var glassFill: Color { Color(red: 0.16, green: 0.12, blue: 0.36).opacity(0.30) }
    static var glassFillStrong: Color { Color(red: 0.16, green: 0.12, blue: 0.36).opacity(0.44) }
    static var glassStroke: Color { Color.white.opacity(0.14) }
    static var glassStrokeHover: Color { Color.white.opacity(0.26) }

    static var onGradientTitle: Color { .white }
    static var onGradientSecondary: Color { Color.white.opacity(0.66) }
}

// MARK: - 通用视图组件

extension View {
    /// 入场淡入上移
    func appearFade(index: Int = 0) -> some View {
        self.opacity(0)
            .offset(y: 6)
            .animation(.easeOut(duration: 0.28).delay(Double(index) * 0.04), value: true)
    }
}

/// 渐变背景上的磨砂卡片
struct GlassCardModifier: ViewModifier {
    var hovered: Bool = false
    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
                    .fill(Design.glassFill)
                    .overlay(
                        RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
                            .stroke(hovered ? Design.glassStrokeHover : Design.glassStroke, lineWidth: 1)
                    )
            )
    }
}

extension View {
    func glassCard(hovered: Bool = false) -> some View {
        modifier(GlassCardModifier(hovered: hovered))
    }
}

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

/// 半透明文字输入框（渐变背景上用）
struct GlassTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: Design.radius, style: .continuous)
                    .fill(Color.white.opacity(0.14))
                    .overlay(
                        RoundedRectangle(cornerRadius: Design.radius, style: .continuous)
                            .stroke(Color.white.opacity(0.18), lineWidth: 1)
                    )
            )
            .foregroundStyle(.white)
    }
}

extension View {
    func glassTextField() -> some View {
        textFieldStyle(GlassTextFieldStyle())
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
