#!/usr/bin/env bash
#
# 本地构建 + 打包 WeChatMP.app + 生成发布 zip 与 sha256。
#
# 用法（二选一）：
#   cd products/wechat-mp/source && bash package_app.sh            # 默认版本 1.0.0
#   cd products/wechat-mp/source && bash package_app.sh 1.0.1      # 指定版本
#
# 产物：
#   products/wechat-mp/releases/<version>/wechat-mp-<version>.zip
#   products/wechat-mp/releases/<version>/wechat-mp-<version>.zip.sha256
#
# 打包完成后，请把 sha256 回填到 manifest.json 的 sha256 字段。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="${1:-1.0.0}"

PRODUCT="wechat-mp"
BUNDLE_NAME="WeChatMP.app"
EXECUTABLE="WeChatMP"

DIST_DIR="${SCRIPT_DIR}/dist"
APP_DIR="${DIST_DIR}/${BUNDLE_NAME}"
RELEASE_DIR="${ROOT_DIR}/releases/${VERSION}"
ZIP_PATH="${RELEASE_DIR}/${PRODUCT}-${VERSION}.zip"
SHA_PATH="${ZIP_PATH}.sha256"

# 安全护栏：只允许清理脚本自身的 dist 目录
if [[ -z "${DIST_DIR}" || "${DIST_DIR}" != */source/dist ]]; then
    echo "[abort] dist 目录异常：${DIST_DIR}" >&2
    exit 1
fi

echo "==> 1/6 编译（release）"
swift build -c release --package-path "${SCRIPT_DIR}"

echo "==> 2/6 组装 ${BUNDLE_NAME}"
rm -rf "${DIST_DIR}"
mkdir -p "${APP_DIR}/Contents/MacOS" "${APP_DIR}/Contents/Resources"

cp "${SCRIPT_DIR}/.build/release/${EXECUTABLE}" "${APP_DIR}/Contents/MacOS/${EXECUTABLE}"
cp "${SCRIPT_DIR}/Info.plist" "${APP_DIR}/Contents/Info.plist"

if [[ -f "${ROOT_DIR}/icon.png" ]]; then
    cp "${ROOT_DIR}/icon.png" "${APP_DIR}/Contents/Resources/icon.png"
fi

echo "==> 3/6 临时签名（ad-hoc）"
codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || {
    echo "[warn] ad-hoc 签名失败，产物仍可用，但首次打开可能需要在「隐私与安全性」中放行。" >&2
}

echo "==> 4/6 打包 zip"
mkdir -p "${RELEASE_DIR}"
rm -f "${ZIP_PATH}" "${SHA_PATH}"
# 仅打包 .app 本体，保持解压后根目录直接是 WeChatMP.app
( cd "${DIST_DIR}" && zip -qry "${ZIP_PATH}" "${BUNDLE_NAME}" )

echo "==> 5/6 计算 sha256"
SHA="$(shasum -a 256 "${ZIP_PATH}" | awk '{print $1}')"
printf '%s  %s\n' "${SHA}" "$(basename "${ZIP_PATH}")" > "${SHA_PATH}"

echo "==> 6/6 完成"
echo "zip      : ${ZIP_PATH}"
echo "sha256   : ${SHA}"
echo
echo "下一步：把上面的 sha256 回填到 ${ROOT_DIR}/manifest.json 的 \"sha256\" 字段，"
echo "       并确认 index.json 的 products[] 中登记值与之逐字一致。"
