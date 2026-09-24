import SwiftUI

/// 账号页：AppID / AppSecret 配置 + 测试连接。
///
/// 凭据仅写入本机私有目录，不写入源码、不进 git、不写入 manifest。
struct AccountView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("公众号凭据")
                            .font(.headline)

                        HStack(spacing: 12) {
                            Text("AppID")
                                .frame(width: 90, alignment: .trailing)
                            TextField("wx0123456789abcdef", text: $state.account.appID)
                                .textFieldStyle(.roundedBorder)
                        }

                        HStack(spacing: 12) {
                            Text("AppSecret")
                                .frame(width: 90, alignment: .trailing)
                            SecureField("在公众平台后台重置后获取", text: $state.account.appSecret)
                                .textFieldStyle(.roundedBorder)
                        }

                        HStack(spacing: 12) {
                            Spacer().frame(width: 90)
                            Button("保存凭据") {
                                state.saveAccount()
                            }
                            .buttonStyle(.borderedProminent)

                            Button("测试连接") {
                                Task { await state.testConnection() }
                            }
                            .disabled(state.isTestingAccount || !state.account.isComplete)

                            if state.isTestingAccount {
                                ProgressView().controlSize(.small)
                            }
                            Spacer()
                        }

                        Text("存储位置（权限 0600，仅当前用户可读写）：\(state.storagePath)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    .padding(8)
                }

                if !state.accountReport.isEmpty {
                    GroupBox("连接检测报告") {
                        Text(state.accountReport)
                            .font(.system(.callout, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                    }
                }

                GroupBox("后台配置要点") {
                    VStack(alignment: .leading, spacing: 8) {
                        bullet("1. 微信公众平台 → 设置与开发 → 基本配置，获取 AppID，重置并保存 AppSecret。")
                        bullet("2. 同一页面「IP 白名单」中加入本机公网出口 IP（终端执行 curl ifconfig.me 获取），否则接口返回 40164。")
                        bullet("3. 草稿接口无需配置服务器 URL / Token，无需开启服务器模式。")
                        bullet("4. 发布接口 freepublish 仅认证的企业订阅号 / 服务号可用；个人主体账号自 2025 年 7 月起已被回收该权限，可创建草稿但需手动发布。")
                        bullet("5. AppSecret 属于高敏感凭据，请勿截图或粘贴到公开渠道；如怀疑泄露请立即在后台重置。")
                    }
                    .padding(8)
                }

                Spacer(minLength: 0)
            }
            .padding(20)
            .frame(maxWidth: 760, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
            Text(text)
                .fixedSize(horizontal: false, vertical: true)
        }
        .font(.callout)
        .foregroundStyle(.secondary)
    }
}
