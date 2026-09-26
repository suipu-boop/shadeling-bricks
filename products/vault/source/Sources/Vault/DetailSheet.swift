import SwiftUI
import BrickUIKit
import LocalAuthentication

/// 资产详情：字段卡片 + AI 摘要 + 敏感字段 Touch ID 解锁 + 删除。
struct DetailSheet: View {
    @ObservedObject var store: VaultStore
    let asset: VaultAsset
    var onChanged: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var unlocked: [String: String] = [:]   // 解密后的敏感字段
    @State private var unlocking = false
    @State private var authError: String?
    @State private var confirmDelete = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Color.white.opacity(0.1))
            ScrollView {
                VStack(alignment: .leading, spacing: Design.Spacing.lg) {
                    titleBlock
                    if !fields.isEmpty { fieldCard(title: "基本信息", rows: fields) }
                    if !sensitiveFields.isEmpty {
                        lockedCard
                    }
                    if let ai = asset.aiSummary, !ai.isEmpty {
                        aiCard
                    }
                    footerActions
                }
                .padding(Design.Spacing.xl)
            }
        }
        .frame(height: 620)   // 宽度由 .brickSheet 统一（规格 v0.1 §1.4）
        .background(Design.appBackgroundGradient)
        .foregroundStyle(.white)
        .brickConfirm(title: "删除这条记录？", confirmLabel: "删除",
                      destructive: true, isPresented: $confirmDelete) { doDelete() }
    }

    // MARK: 区块

    private var header: some View {
        HStack {
            Text("资产详情").font(.system(size: 15, weight: .bold))
            Spacer()
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.system(size: 12, weight: .semibold))
                    .padding(6).background(Circle().fill(Color.white.opacity(0.14)))
            }
            .buttonStyle(.plain)
        }
        .padding(Design.Spacing.lg)
    }

    private var titleBlock: some View {
        HStack(alignment: .top, spacing: 12) {
            Circle().fill(typeColor(asset.type)).frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 4) {
                Text(asset.title).font(.system(size: 17, weight: .bold)).lineLimit(2)
                Text("\(typeLabel(asset.type)) · \(asset.isFromAI ? "AI 沉淀" : "手动录入") · 更新于 \(fmt(asset.updatedAt))")
                    .font(.system(size: 11)).foregroundStyle(Design.onGradientSecondary)
            }
            Spacer()
        }
    }

    private var fields: [(String, String)] {
        var rows: [(String, String)] = []
        switch asset.type {
        case "document":
            rows += [("证件类型", asset.docType ?? ""),
                     ("签发方", asset.issuer ?? ""),
                     ("生效日期", asset.validFrom ?? ""),
                     ("到期日期", asset.validTo ?? ""),
                     ("编号(掩码)", asset.numberMasked ?? "")]
        case "webpage":
            if let url = asset.url { rows.append(("网址", url)) }
            if let src = asset.source, !asset.isFromAI { rows.append(("来源", src)) }
            if let excerpt = asset.excerpt { rows.append(("摘要", excerpt)) }
        case "skill_snapshot":
            rows += [("类别", asset.category ?? ""), ("版本", asset.version ?? ""),
                     ("说明", asset.skillDesc ?? "")]
        case "note":
            if let name = asset.notesAccountName { rows.append(("账户", name)) }
            if let url = asset.url { rows.append(("网址", url)) }
            if let text = asset.text { rows.append(("内容", text)) }
        default: break
        }
        if let d = asset.desc, !d.isEmpty { rows.append(("备注", d)) }
        if !asset.tags.isEmpty { rows.append(("标签", asset.tags.joined(separator: "、"))) }
        return rows.filter { !$0.1.isEmpty }
    }

    private var sensitiveFields: [String] {
        asset.hasSensitive ? ["number_full", "password"] : []
    }

    private var lockedCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "lock.shield.fill").foregroundStyle(.yellow.opacity(0.95))
                Text("敏感字段已加密")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
            }
            if !unlocked.isEmpty {
                ForEach(Array(unlocked.keys), id: \.self) { k in
                    HStack(alignment: .top) {
                        Text(label(for: k)).font(.system(size: 12))
                            .foregroundStyle(Design.onGradientSecondary).frame(width: 90, alignment: .leading)
                        Text(unlocked[k] ?? "")
                            .font(.system(size: 13, weight: .medium))
                            .textSelection(.enabled)
                            .fontWidth(.init(0.9))
                        Spacer()
                    }
                    .padding(8)
                    .background(RoundedRectangle(cornerRadius: Design.radius).fill(Color.white.opacity(0.08)))
                }
            } else if unlocking {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("正在验证…").font(.system(size: 12)).foregroundStyle(Design.onGradientSecondary)
                }
            } else {
                Button {
                    authenticate()
                } label: {
                    Label("Touch ID / 密码验证后查看", systemImage: "faceid")
                        .font(.system(size: 12, weight: .medium))
                }
                .glassButton()
                if let authError {
                    Text(authError).font(.system(size: 11)).foregroundStyle(.red.opacity(0.9))
                }
            }
        }
        .padding(Design.Spacing.md)
        .background(RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
            .fill(Color.yellow.opacity(0.07)))
        .overlay(RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
            .stroke(Color.yellow.opacity(0.2), lineWidth: 1))
    }

    private var aiCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles").foregroundStyle(Design.ColorPalette.accent)
                Text("AI 摘要").font(.system(size: 13, weight: .semibold))
            }
            Text(asset.aiSummary ?? "").font(.system(size: 12, weight: .regular)).lineSpacing(3)
            if !asset.aiTags.isEmpty {
                HStack(spacing: 6) {
                    ForEach(asset.aiTags, id: \.self) { tag in
                        Text("#\(tag)")
                            .font(.system(size: 10))
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(Capsule().fill(Design.ColorPalette.accent.opacity(0.28)))
                    }
                }
            }
        }
        .padding(Design.Spacing.md)
        .background(RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
            .fill(Design.ColorPalette.accent.opacity(0.1)))
        .overlay(RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
            .stroke(Design.ColorPalette.accent.opacity(0.25), lineWidth: 1))
    }

    private var footerActions: some View {
        HStack {
            Spacer()
            Button(role: .destructive) {
                confirmDelete = true
            } label: {
                Label("删除", systemImage: "trash")
            }
            .buttonStyle(.plain)
            .font(.system(size: 12))
            .foregroundStyle(.red.opacity(0.9))
            .padding(6)
        }
    }

    // MARK: 逻辑

    private func fieldCard(title: String, rows: [(String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.system(size: 13, weight: .semibold))
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top) {
                    Text(row.0).font(.system(size: 12))
                        .foregroundStyle(Design.onGradientSecondary).frame(width: 90, alignment: .leading)
                    Text(row.1).font(.system(size: 13)).textSelection(.enabled)
                    Spacer()
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: Design.radius).fill(Color.white.opacity(0.08)))
            }
        }
    }

    private func label(for k: String) -> String {
        switch k {
        case "number_full": return "证件号码"
        case "password": return "口令"
        default: return k
        }
    }

    private func authenticate() {
        authError = nil
        unlocking = true
        let ctx = LAContext()
        var err: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) else {
            authError = "当前设备未启用密码/Touch ID"
            unlocking = false
            return
        }
        ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "解锁 Vault 敏感字段") { ok, e in
            DispatchQueue.main.async {
                unlocking = false
                if ok {
                    do {
                        unlocked = try store.plainFields(id: asset.id)
                        if unlocked.isEmpty { authError = "未找到可解密的敏感字段" }
                    } catch {
                        authError = error.localizedDescription
                    }
                } else {
                    authError = "验证未通过"
                }
            }
        }
    }

    private func doDelete() {
        store.delete(id: asset.id)
        onChanged()
        dismiss()
    }

    private func fmt(_ ts: Double) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.string(from: Date(timeIntervalSince1970: ts))
    }
}

#Preview {
    DetailSheet(store: (try? VaultStore())!, asset: VaultAsset(id: "x", type: "document", title: "示例",
                                                               createdAt: 0, updatedAt: 0))
}
