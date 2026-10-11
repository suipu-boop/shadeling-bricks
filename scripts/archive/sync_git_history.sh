#!/usr/bin/env bash
# 把本地 brick-vault 的完整 git 历史打包成 bundle，并同步到 iCloud 镜像。
#
# 安全设计（不改动 backup_to_icloud.sh 的镜像语义）：
#   - bundle 生成在本地 .icloud_history/（已写入 .gitignore，不污染版本库）
#   - 由随后的 rsync 镜像正常推送；源端有该文件，--delete 不会误删
#   - bundle 仅含 git 历史压缩包，不塞大文件
#
# 顺序纪律（与 Shadeling 侧一致，不可颠倒）：
#   必须先本脚本（生成 bundle）→ 再由 backup_to_icloud.sh 镜像；
#   若先镜像后补 bundle，rsync --delete 会误删镜像里尚未存在的 bundle。
#
# 还原（跨设备回到 Mac 时）：
#   git clone /path/to/brick-vault.bundle  ~/somewhere/brick-vault_restore
set -euo pipefail

# 注意：本脚本已归档至 scripts/archive/，故 ROOT 需上溯两级到仓库根
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p .icloud_history
git bundle create .icloud_history/brick-vault.bundle --all
echo "✅ git 历史 bundle 已生成: .icloud_history/brick-vault.bundle ($(du -h .icloud_history/brick-vault.bundle | cut -f1))"

# 复用已验证的 iCloud 镜像脚本（含 --delete，但 bundle 源端存在故安全）
bash "$ROOT/scripts/backup_to_icloud.sh"
