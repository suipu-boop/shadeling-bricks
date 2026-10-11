#!/usr/bin/env bash
# brick-vault 本地仓库 → iCloud 备份（源码快照，排除大文件/构建产物/缓存）
#
# 策略（与 Shadeling 侧 scripts/backup_to_icloud.sh 同等能力，口径对齐）：
#   活跃仓库在本地 ~/Dev/brick-vault，每个里程碑跑一次本脚本，把源码镜像到 iCloud。
#   iCloud 只存工作区源码快照（不含 .git 历史、不含模型/大库）；git 历史由
#   scripts/archive/sync_git_history.sh 生成的 bundle（.icloud_history/）一并携带，
#   该脚本必须早于本脚本执行（顺序不可颠倒，详见 state-2026-10-11.md §30）。
#
# 2026-10-11 移植自 Shadeling：保留三层加固——① brctl 唤醒镜像目录；② rsync 退避
# 重试（30s/60s/90s）；③ 失败时定点唤醒 + 逐文件兜底（mirror_icloud_fallback.py）。
set -uo pipefail

SRC="$HOME/Dev/brick-vault"
DST="$HOME/Library/Mobile Documents/com~apple~CloudDocs/brick-vault"

EXCLUDES=(
  --exclude='.git'
  --exclude='.build'
  --exclude='build'
  --exclude='DerivedData'
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='.pytest_cache'
  --exclude='.venv'
  --exclude='*.egg-info'
  --exclude='models'
  --exclude='*.db'
  --exclude='*.db-wal'
  --exclude='*.db-shm'
  --exclude='.DS_Store'
  --exclude='backup'
)

mkdir -p "$DST"

# 第 1 层：唤醒镜像目录（过渡态文件促下发，释放 File Provider 锁）
if command -v brctl >/dev/null 2>&1; then
  brctl download "$DST" >/dev/null 2>&1 || true
  sleep 3
fi

# 第 2/3 层：退避重试，失败时定点唤醒报错文件
run_rsync() {
  rsync -av --delete "${EXCLUDES[@]}" "$SRC/" "$DST/" 2>&1
}

attempt=1
max_attempts=4
waits=(30 60 90)
while true; do
  output=$(run_rsync)
  status=$?
  if [ $status -eq 0 ]; then
    break
  fi

  # 提取报错文件做定点唤醒（mmap deadlock 特征才值得重试，其他错误只重试一次）
  deadlock=$(printf '%s' "$output" | grep -c "Resource deadlock avoided" || true)
  if command -v brctl >/dev/null 2>&1; then
    printf '%s' "$output" | grep -oE "error: [^:]+\.([a-zA-Z0-9]+): mmap" | \
      sed -E 's/error: (.+): mmap/\1/' | while IFS= read -r f; do
        brctl download "$DST/$f" >/dev/null 2>&1 || true
      done
  fi

  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "⚠️  rsync 连续 ${max_attempts} 次失败（iCloud File Provider 过渡锁），降级到逐文件兜底镜像..."
    printf '%s\n' "$output" | grep -E "^rsync.*error" | head -5 >&2
    if [ -f "$SRC/scripts/mirror_icloud_fallback.py" ]; then
      if python3 "$SRC/scripts/mirror_icloud_fallback.py"; then
        echo ""
        echo "✅ brick-vault 源码已备份到 iCloud（rsync 失败 → 逐文件兜底成功）: ${DST}"
        echo "   （不含 .git 历史 / 模型权重 / 数据库，这些留本地）"
        exit 0
      else
        echo "❌ 逐文件兜底镜像仍有失败（见上方清单），可稍后重跑本脚本" >&2
        exit 1
      fi
    fi
    echo "❌ iCloud 备份失败（已重试 $((max_attempts - 1)) 次，且未找到兜底脚本）" >&2
    exit $status
  fi

  wait=${waits[$((attempt - 1))]}
  echo "⏳ rsync 失败（第 $attempt 次，deadlock 命中 $deadlock 处），${wait}s 后重试..."
  sleep "$wait"
  attempt=$((attempt + 1))
done

echo ""
echo "✅ brick-vault 源码已备份到 iCloud: ${DST}（第 $attempt 次尝试成功）"
echo "   （不含 .git 历史 / 模型权重 / 数据库，这些留本地）"
