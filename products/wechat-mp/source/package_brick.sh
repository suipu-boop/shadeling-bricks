#!/usr/bin/env bash
# wechat-mp（brick-app/v2 声明式）出包入口：manifest.json + ui/ + logic/（无 .app bundle）
#
# v1（bundle 形态）出包仍是 source/package_app.sh；v2 起改由 scripts/pack_product.py 的
# `pack` 子命令产出包，再由 `finalize` 算 sha256 回填 manifest.json / index.json，
# 最后跑产品闸门 verify_products.py 确认合规（契约 §3.3 / §3.6）。
set -euo pipefail

VAULT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
MANIFEST="${VAULT_DIR}/products/wechat-mp/manifest.json"
VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "${MANIFEST}")"

echo "==> 1/3 出包（v2 三段：manifest.json + ui + logic），版本 ${VERSION}"
python3 "${VAULT_DIR}/scripts/pack_product.py" pack --product wechat-mp --version "${VERSION}"

echo "==> 2/3 算 sha256 并回填 manifest.json / index.json"
python3 "${VAULT_DIR}/scripts/pack_product.py" finalize --product wechat-mp --version "${VERSION}"

echo "==> 3/3 产品闸门复核"
python3 "${VAULT_DIR}/scripts/verify_products.py" wechat-mp

echo "==> 完成：products/wechat-mp/releases/${VERSION}/wechat-mp-${VERSION}.zip"
