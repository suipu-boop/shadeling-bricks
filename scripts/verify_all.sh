#!/usr/bin/env bash
# 单入口闸门（Phase 4 配套）：ui 文档规则表 → 产品发布闸门 → 内核积木闸门
#
#   bash scripts/verify_all.sh              # 全量
#   bash scripts/verify_all.sh --ui-only    # 只跑 ui 文档规则表（改 UI 时的高频回路）
#   BRICK_VAULT_ROOT=/tmp/x bash scripts/verify_all.sh   # 指向临时 vault（CI / 脚手架自测）
#
# 阶段口径（重要）：新产品在出包（pack + finalize）之前，release zip 与 index.json 登记项
# 必然缺失——属阶段差异、非缺陷；「生成即自检」由 scripts/new_product.py 承担，
# 本脚本是**发布前**的总闸门。
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="${BRICK_VAULT_ROOT:-$(cd "$SCRIPTS_DIR/.." && pwd)}"
cd "$VAULT_ROOT" || exit 1

ui_only=0
for arg in "$@"; do
  case "$arg" in
    --ui-only) ui_only=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg"; exit 2 ;;
  esac
done

fail=0
shopt -s nullglob

echo "== [1/3] ui 文档规则表（结构 + 令牌表硬校验，对齐 Swift UIDocumentValidator） =="
docs=("$VAULT_ROOT"/products/*/ui/main.json)
if [ ${#docs[@]} -eq 0 ]; then
  echo "  （products/*/ui/main.json 为空，跳过）"
else
  for f in "${docs[@]}"; do
    python3 "$SCRIPTS_DIR/verify_ui_doc.py" "$f" || fail=1
  done
fi

if [ "$ui_only" -eq 1 ]; then
  if [ "$fail" -eq 0 ]; then echo "== verify_all（ui-only）：通过 =="; else echo "== verify_all（ui-only）：未通过 =="; fi
  exit "$fail"
fi

echo "== [2/3] 产品发布闸门（brick-app/v2：manifest / zip / index 对齐 / 源码闸门） =="
python3 "$SCRIPTS_DIR/verify_products.py" || fail=1

echo "== [3/3] 内核积木闸门（bricks/，镜像 runtime/skill_library.py） =="
if [ -d "$VAULT_ROOT/bricks" ] && [ -f "$SCRIPTS_DIR/verify_bricks.py" ]; then
  python3 "$SCRIPTS_DIR/verify_bricks.py" || fail=1
else
  echo "  （未发现 scripts/verify_bricks.py，跳过）"
fi

if [ "$fail" -eq 0 ]; then
  echo "== verify_all：全部闸门通过 =="
else
  echo "== verify_all：存在未通过闸门（详见上） =="
fi
exit "$fail"
