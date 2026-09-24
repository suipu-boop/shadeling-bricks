import SwiftUI
import LocalAuthentication

/// 手动录入渠道：按类型动态表单，敏感字段加密入库。
struct ManualAddSheet: View {
    @ObservedObject var store: VaultStore
    var onSaved: () -> Void = {}

    @Environment(\.dismiss) private var dismiss

    @State private var kind: ManualKind = .document("身份证")
    @State private var titleOverride = ""
    @State private var specs: [VaultFieldSpec] = ManualTemplate.spec(for: .document("身份证"))
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Color.white.opacity(0.1))
            ScrollView { form }
            Divider().overlay(Color.white.opacity(0.1))
            footer
        }
        .frame(width: 460, height: 560)
        .background(Design.appBackgroundGradient)
        .foregroundStyle(.white)
    }

    private var header: some View {
        HStack {
            Text("手动新增")
                .font(.system(size: 15, weight: .bold))
            Spacer()
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .padding(6)
                    .background(Circle().fill(Color.white.opacity(0.14)))
            }
            .buttonStyle(.plain)
        }
        .padding(Design.Spacing.lg)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 16) {
            // 类型选择
            VStack(alignment: .leading, spacing: 8) {
                Text("类型").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Design.onGradientSecondary)
                HStack(spacing: 8) {
                    typeChip(.account)
                    typeChip(.webpage)
                    typeChip(.note)
                }
                if case .document = kind {
                    Picker("证件类型", selection: Binding(
                        get: { docTypeSelection },
                        set: { newValue in kind = .document(newValue); rebuild() }
                    )) {
                        ForEach(ManualTemplate.documentTypeOptions, id: \.self) { t in
                            Text(t).tag(t)
                        }
                    }
                    .pickerStyle(.menu)
                    .labelsHidden()
                    .frame(width: 180)
                } else {
                    typeChip(.document("身份证"))
                }
            }

            // 动态字段
            VStack(alignment: .leading, spacing: 10) {
                Text("内容").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Design.onGradientSecondary)
                ForEach($specs) { $spec in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(spec.label)
                                .font(.system(size: 11))
                                .foregroundStyle(Design.onGradientSecondary)
                            if spec.sensitive {
                                Image(systemName: "lock.fill").font(.system(size: 9))
                                    .foregroundStyle(.yellow.opacity(0.9))
                                Text("加密存储").font(.system(size: 10))
                                    .foregroundStyle(.yellow.opacity(0.8))
                            }
                        }
                        if spec.id == "text" {
                            TextEditor(text: $spec.value)
                                .font(.system(size: 13))
                                .scrollContentBackground(.hidden)
                                .padding(8)
                                .frame(height: 90)
                                .background(RoundedRectangle(cornerRadius: Design.radius).fill(Color.white.opacity(0.12)))
                                .overlay(RoundedRectangle(cornerRadius: Design.radius).stroke(Color.white.opacity(0.16)))
                        } else {
                            TextField(spec.placeholder, text: $spec.value)
                                .textFieldStyle(.plain)
                                .font(.system(size: 13))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 7)
                                .background(RoundedRectangle(cornerRadius: Design.radius).fill(Color.white.opacity(0.12)))
                                .overlay(RoundedRectangle(cornerRadius: Design.radius).stroke(Color.white.opacity(0.16)))
                        }
                    }
                }
            }

            if let error {
                Text(error).font(.system(size: 11)).foregroundStyle(.red.opacity(0.95))
            }
        }
        .padding(Design.Spacing.lg)
    }

    private var footer: some View {
        HStack {
            Spacer()
            Button("取消") { dismiss() }
                .glassButton()
            Button {
                save()
            } label: {
                if saving { ProgressView().controlSize(.small).tint(.white) }
                else { Text("存入 Vault") }
            }
            .glassButton(prominent: true)
            .disabled(saving)
        }
        .padding(Design.Spacing.lg)
    }

    // MARK: - 逻辑

    private var docTypeSelection: String {
        if case .document(let t) = kind { return t }
        return "身份证"
    }

    private func typeChip(_ k: ManualKind) -> some View {
        let active: Bool = {
            switch (kind, k) {
            case (.document, .document): return true
            case (.account, .account), (.webpage, .webpage), (.note, .note): return true
            default: return false
            }
        }()
        return Button {
            kind = k
            rebuild()
        } label: {
            Text(k.label)
                .font(.system(size: 12, weight: active ? .semibold : .regular))
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Capsule().fill(active ? Color.white.opacity(0.28) : Color.white.opacity(0.08)))
                .overlay(Capsule().stroke(active ? Color.white.opacity(0.3) : Color.white.opacity(0.1), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func rebuild() {
        specs = ManualTemplate.spec(for: kind)
        titleOverride = ""
    }

    private func save() {
        saving = true
        error = nil
        defer { saving = false }
        var fields: [String: String] = [:]
        var sensitive: [String: String] = [:]
        for s in specs {
            let v = s.value.trimmingCharacters(in: .whitespacesAndNewlines)
            if v.isEmpty { continue }
            if s.sensitive {
                sensitive[s.id] = v
            } else {
                fields[s.id] = v
            }
        }
        // 标题：优先 titleOverride，否则由 store 生成
        let title = titleOverride.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let asset = try store.add(type: kind.type, title: title.isEmpty ? nil : title,
                                      fields: fields, sensitive: sensitive, source: nil)
            onSaved()
            dismiss()
            _ = asset
        } catch {
            self.error = error.localizedDescription
        }
    }
}

#Preview {
    ManualAddSheet(store: (try? VaultStore())!)
}
