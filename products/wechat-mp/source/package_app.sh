#!/usr/bin/env bash
#
# 本地构建 + 打包 WeChatMP.app + 生成发布 zip 与 sha256。
#
# 用法（二选一）：
#   cd products/wechat-mp/source && bash package_app.sh            # 默认版本 1.1.0
#   cd products/wechat-mp/source && bash package_app.sh 1.1.1      # 指定版本
#
# 前置：Shadeling 仓需位于 ~/Dev/Shadeling（BrickUIKit 为跨仓本地 SPM 依赖，缺失即 abort）。
#
# 产物：
#   products/wechat-mp/releases/<version>/wechat-mp-<version>.zip
#   products/wechat-mp/releases/<version>/wechat-mp-<version>.zip.sha256
#
# 打包完成后由 scripts/pack_product.py finalize 自动回填 sha256（manifest.json + index.json）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VAULT_DIR="$(cd "${ROOT_DIR}/../.." && pwd)"
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

# 步骤 0：依赖前置检查（规格 v0.1 §1.1）——BrickUIKit 走跨仓相对路径，
# 路径不存在时必须在编译前 abort，避免报出难懂的 SPM 解析错误。
BRICKUIKIT_DIR="${SCRIPT_DIR}/../../../../Shadeling/app/packages/BrickUIKit"
if [[ ! -f "${BRICKUIKIT_DIR}/Package.swift" ]]; then
    echo "[abort] 缺少 BrickUIKit 依赖：${BRICKUIKIT_DIR}/Package.swift 不存在。" >&2
    echo "        该依赖按跨仓相对路径引用，要求 Shadeling 仓位于 ~/Dev/Shadeling（规格 v0.1 §1.1）。" >&2
    exit 1
fi

echo "==> 1/7 依赖前置检查（BrickUIKit）通过"
swift build -c release --package-path "${SCRIPT_DIR}"

echo "==> 2/7 组装 ${BUNDLE_NAME}"
rm -rf "${DIST_DIR}"
mkdir -p "${APP_DIR}/Contents/MacOS" "${APP_DIR}/Contents/Resources"

cp "${SCRIPT_DIR}/.build/release/${EXECUTABLE}" "${APP_DIR}/Contents/MacOS/${EXECUTABLE}"
cp "${SCRIPT_DIR}/Info.plist" "${APP_DIR}/Contents/Info.plist"

if [[ -f "${ROOT_DIR}/icon.png" ]]; then
    cp "${ROOT_DIR}/icon.png" "${APP_DIR}/Contents/Resources/icon.png"
fi

echo "==> 3/7 临时签名（ad-hoc）"
codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || {
    echo "[warn] ad-hoc 签名失败，产物仍可用，但首次打开可能需要在「隐私与安全性」中放行。" >&2
}

echo "==> 4/7 暂存包内 manifest.json"
# 安装器解压后必须能读到包内 manifest 才能确认身份 / 入口 bundle / 权限声明，缺了直接中止安装
# （实测：zip 只含 .app 本体时 wechat-mp / vault 两只包都装不上）。
# 包内 manifest 只带身份字段：sha256 / download_url 是仓库侧发布元数据，且 zip 无法含自身哈希。
python3 "${VAULT_DIR}/scripts/pack_product.py" stage \
    --product "${PRODUCT}" --out "${DIST_DIR}/manifest.json"

echo "==> 5/7 打包 zip（.app 本体 + manifest.json）"
mkdir -p "${RELEASE_DIR}"
rm -f "${ZIP_PATH}" "${SHA_PATH}"
( cd "${DIST_DIR}" && zip -qry "${ZIP_PATH}" "${BUNDLE_NAME}" manifest.json )

echo "==> 6/7 算 sha256 + 回填 manifest.json / index.json（含 zip 内容复核）"
python3 "${VAULT_DIR}/scripts/pack_product.py" finalize \
    --product "${PRODUCT}" --version "${VERSION}"

echo "==> 完成"
echo "zip    : ${ZIP_PATH}"
echo "复核   : cd ${VAULT_DIR} && python3 scripts/verify_products.py ${PRODUCT}"
