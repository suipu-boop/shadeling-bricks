#!/usr/bin/env python3
"""iCloud 源码镜像兜底（纯读写逐文件复制，绕开 rsync mmap 死锁）。

背景（2026-10-02 实战，Shadeling 侧沉淀）：
  macOS iCloud File Provider 对处于「过渡态」的文件加锁。rsync 用 mmap 读源端
  时会命中 `Resource deadlock avoided (EDEADLK)` 并**整批 abort**，且每次失败
  的文件不同（过渡态在整片区域游走），导致 backup_to_icloud.sh 的 4 次退避重试
  也永远跑不完。

本脚本的对策（2026-10-11 移植自 Shadeling，路径改为 brick-vault）：
  1. 不用 rsync，改纯 read/write（shutil.copy，不走 mmap）；
  2. **目标已存在时先 unlink 再拷**——旧文件被过渡锁占用时直接覆盖写命 EDEADLK，
     删旧建新可绕开（实测把失败数从 217 直接打到 0）；
  3. 逐文件容错：单文件失败只记一笔，不拖垮整批；末尾打印失败清单供定点重试；
  4. 末尾清理 DST 中源端已不存在的陈旧文件，保持镜像语义（等价 rsync --delete）。

用法：python3 scripts/mirror_icloud_fallback.py
退出码：0 全部成功；1 有失败（见 stdout 清单）。
"""
import os
import shutil
import sys
from pathlib import Path

SRC = Path.home() / "Dev" / "brick-vault"
DST = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/brick-vault"

# 与 backup_to_icloud.sh 的 EXCLUDES 保持一致
EXCLUDE_NAMES = {".git", ".build", "build", "DerivedData", "__pycache__",
                 ".pytest_cache", ".venv", "models", "backup"}
EXCLUDE_SUFFIX = (".pyc", ".egg-info", ".db", ".db-wal", ".db-shm", ".DS_Store")


def excluded(name: str) -> bool:
    return name in EXCLUDE_NAMES or name.endswith(EXCLUDE_SUFFIX)


def walk_rel(root: Path):
    """产出 (相对路径, 是否目录)，跳过被排除项。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not excluded(d)]
        rel_dir = os.path.relpath(dirpath, root)
        for d in dirnames:
            yield os.path.join(rel_dir, d), True
        for f in filenames:
            if excluded(f):
                continue
            yield os.path.join(rel_dir, f), False


def main() -> int:
    if not SRC.is_dir():
        print(f"源目录不存在: {SRC}")
        return 1
    DST.mkdir(parents=True, exist_ok=True)

    copied = fail = 0
    failures = []
    src_files = set()

    for rel, is_dir in walk_rel(SRC):
        if rel == ".":
            continue
        s, d = SRC / rel, DST / rel
        if is_dir:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                failures.append((rel, f"mkdir: {e}"))
                fail += 1
            continue
        src_files.add(rel)
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            # 目标已存在时先删再拷（旧文件过渡锁 → 直接覆盖写会 EDEADLK）
            if d.exists() or d.is_symlink():
                try:
                    d.unlink()
                except Exception:
                    pass
            shutil.copy(s, d)
            copied += 1
        except Exception as e:
            fail += 1
            failures.append((rel, f"{type(e).__name__}: {e}"))

    removed = 0
    rem_fail = []
    for rel, is_dir in walk_rel(DST):
        if rel == "." or is_dir:
            continue
        if rel not in src_files:
            try:
                (DST / rel).unlink()
                removed += 1
            except Exception as e:
                rem_fail.append((rel, str(e)))

    print(f"copied={copied} failed={fail} removed={removed} rem_fail={len(rem_fail)}")
    if failures:
        print("=== 复制失败（前 20）===")
        for rel, err in failures[:20]:
            print(f"  {rel}: {err}")
    if rem_fail:
        print("=== 清理失败（前 10）===")
        for rel, err in rem_fail[:10]:
            print(f"  {rel}: {err}")
    return 0 if fail == 0 and not rem_fail else 1


if __name__ == "__main__":
    sys.exit(main())
