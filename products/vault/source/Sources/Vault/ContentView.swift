import SwiftUI
import BrickUIKit

/// 主界面：粉紫玻璃风资产中枢。
/// 命令栏（搜索 / 手动新增 / 刷新） + 类型筛选 + 卡片墙 + 详情/录入弹层。
struct ContentView: View {
    @StateObject private var store: VaultStore
    @State private var searchText = ""
    @State private var filter: String? = nil
    @State private var selected: VaultAsset?
    @State private var showManualAdd = false
    @State private var hoverCard: String?

    private static let filters: [(id: String?, label: String)] = [
        (nil, "全部"), ("document", "证件"), ("image", "图片"),
        ("webpage", "收藏"), ("skill_snapshot", "技能"), ("note", "笔记"), ("ai", "AI 沉淀")
    ]

    init() {
        let store = (try? VaultStore()) ?? { fatalError("Vault 存储初始化失败") }()
        _store = StateObject(wrappedValue: store)
    }

    var body: some View {
        ZStack {
            Design.appBackgroundGradient.ignoresSafeArea()
            VStack(spacing: 0) {
                commandBar
                Divider().overlay(Color.white.opacity(0.1))
                filterBar
                ScrollView {
                    cardGrid
                }
                .scrollIndicators(.hidden)
            }
            .background(VaultGlass.fill.opacity(0.55))
        }
        .foregroundStyle(.white)
        .task { store.reload() }
        .onChange(of: searchText) { _, _ in applyQuery() }
        .onChange(of: filter) { _, _ in applyQuery() }
        .brickSheet(isPresented: $showManualAdd) {
            ManualAddSheet(store: store) { store.reload() }
        }
        .brickSheet(isPresented: detailPresented) {
            if let asset = selected {
                DetailSheet(store: store, asset: asset) { store.reload() }
            }
        }
    }

    private func applyQuery() {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let type = (filter == "ai" || filter == nil) ? nil : filter
        store.reload(type: type, q: q.isEmpty ? nil : q)
    }

    /// `.brickSheet` 只提供 `isPresented` 形态，详情弹层由可选值派生绑定（规格 v0.1 §1.4）。
    private var detailPresented: Binding<Bool> {
        Binding(get: { selected != nil }, set: { if !$0 { selected = nil } })
    }

    // MARK: 命令栏

    private var commandBar: some View {
        HStack(spacing: Design.Spacing.md) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Vault")
                    .font(.system(size: 17, weight: .bold))
                Text("本地资产中枢 · \(store.items.count) 条")
                    .font(.system(size: 11))
                    .foregroundStyle(Design.onGradientSecondary)
            }
            Spacer()
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(Design.onGradientSecondary)
                TextField("查找资产 / 网址 / 内容", text: $searchText)
                    .textFieldStyle(.plain)
                    .frame(width: 220)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Capsule().fill(Color.white.opacity(0.14)))
            .overlay(Capsule().stroke(Color.white.opacity(0.16), lineWidth: 1))

            Button {
                showManualAdd = true
            } label: {
                Label("手动新增", systemImage: "plus")
            }
            .glassButton(prominent: true)

            Button {
                store.reload()
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .glassButton()
            .help("刷新")
        }
        .padding(.horizontal, Design.Spacing.xl)
        .padding(.vertical, 14)
    }

    // MARK: 筛选

    private var filterBar: some View {
        HStack(spacing: 8) {
            ForEach(Self.filters, id: \.label) { f in
                let active = (filter == f.id)
                Button {
                    filter = f.id
                } label: {
                    Text(f.label)
                        .font(.system(size: 12, weight: active ? .semibold : .regular))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(Capsule().fill(active ? Color.white.opacity(0.26) : Color.white.opacity(0.08)))
                        .overlay(Capsule().stroke(active ? Color.white.opacity(0.3) : Color.white.opacity(0.1),
                                                  lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            Spacer()
            if let err = store.lastError {
                Text(err).font(.system(size: 11)).foregroundStyle(.red.opacity(0.9))
            }
        }
        .padding(.horizontal, Design.Spacing.xl)
        .padding(.vertical, 10)
    }

    // MARK: 卡片墙

    private var filteredItems: [VaultAsset] {
        if filter == "ai" { return store.items.filter { $0.isFromAI } }
        if let filter, filter != "ai" { return store.items.filter { $0.type == filter } }
        return store.items
    }

    private var cardGrid: some View {
        let cols = [GridItem(.adaptive(minimum: 190, maximum: 260), spacing: 14)]
        return LazyVGrid(columns: cols, spacing: 14) {
            ForEach(filteredItems) { asset in
                AssetCard(asset: asset, hovered: hoverCard == asset.id)
                    .onHover { hoverCard = $0 ? asset.id : nil }
                    .contentShape(RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous))
                    .onTapGesture { selected = asset }
            }
        }
        .padding(Design.Spacing.xl)
    }
}

// MARK: - 资产卡片

struct AssetCard: View {
    let asset: VaultAsset
    var hovered: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(typeColor(asset.type))
                    .frame(width: 8, height: 8)
                Text(typeLabel(asset.type))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Design.onGradientSecondary)
                Spacer()
                if asset.isFromAI {
                    Text("AI")
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Design.ColorPalette.accent.opacity(0.35)))
                        .overlay(Capsule().stroke(Color.white.opacity(0.2), lineWidth: 0.5))
                }
                if asset.hasSensitive {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(.yellow.opacity(0.85))
                }
            }
            Text(asset.title)
                .font(.system(size: 14, weight: .semibold))
                .lineLimit(1)
            if !asset.subtitle.isEmpty {
                Text(asset.subtitle)
                    .font(.system(size: 11))
                    .foregroundStyle(Design.onGradientSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            HStack {
                Text(relativeTime(asset.updatedAt))
                    .font(.system(size: 10))
                    .foregroundStyle(Design.onGradientSecondary.opacity(0.8))
                Spacer()
            }
        }
        .padding(Design.Spacing.md)
        .frame(minHeight: 96, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
                .fill(hovered ? VaultGlass.fillStrong : VaultGlass.fill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Design.radiusLg, style: .continuous)
                .stroke(hovered ? VaultGlass.strokeHover : VaultGlass.stroke, lineWidth: 1)
        )
        .animation(.easeOut(duration: 0.15), value: hovered)
    }

    private func relativeTime(_ ts: Double) -> String {
        let d = Date(timeIntervalSince1970: ts)
        let f = RelativeDateTimeFormatter()
        f.locale = Locale(identifier: "zh_CN")
        return f.localizedString(for: d, relativeTo: Date())
    }
}

// MARK: - 空态

#Preview {
    ContentView()
}
