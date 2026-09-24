import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// 素材页：上传图片到永久素材 + 素材库缓存。
struct MediaView: View {
    @EnvironmentObject private var state: AppState
    @State private var isImporterPresented = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                Button("上传图片到永久素材") {
                    isImporterPresented = true
                }
                .buttonStyle(.borderedProminent)
                .disabled(state.isBusy || !state.account.isComplete)

                Text("支持 JPG / PNG / GIF / BMP / WebP，单张 ≤ 10 MB")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer()

                Text("共 \(state.mediaAssets.count) 个素材")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            if state.mediaAssets.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "photo.on.rectangle.angled")
                        .font(.system(size: 36))
                        .foregroundStyle(.tertiary)
                    Text("暂无素材。上传后的图片会获得 media_id，可作为草稿封面复用。")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(state.mediaAssets) { asset in
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(asset.fileName)
                                    .font(.headline)
                                Text("media_id：\(asset.mediaID)")
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                if !asset.imageURL.isEmpty {
                                    Text(asset.imageURL)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                        .textSelection(.enabled)
                                }
                            }
                            Spacer()
                            Text(asset.uploadedAt.formatted(date: .numeric, time: .shortened))
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Button("设为封面") {
                                state.payload.thumbMediaID = asset.mediaID
                                state.notice = "已将 \(asset.fileName) 设为草稿封面。"
                                state.noticeIsError = false
                            }

                            Button("复制 media_id") {
                                let pasteboard = NSPasteboard.general
                                pasteboard.clearContents()
                                pasteboard.setString(asset.mediaID, forType: .string)
                                state.notice = "media_id 已复制到剪贴板。"
                                state.noticeIsError = false
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .fileImporter(
            isPresented: $isImporterPresented,
            allowedContentTypes: [.image],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                Task { await state.uploadImage(at: url) }
            case .failure(let error):
                state.notice = "选择图片失败：\(error.localizedDescription)"
                state.noticeIsError = true
            }
        }
    }
}
