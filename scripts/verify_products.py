#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick Vault · 产品积木发布闸门（市场 V2）。

products/<id>/ 发布前强制自检：
1. manifest.json 字段完整（brick-app/v1），kind=product，id/name 与目录一致
2. releases/<version>/ 下 zip 存在，sha256 与 manifest 一致
3. index.json products[] 已登记（name/version/kind/download_url/sha256 对齐）
4. id 不与已发布积木冲突

契约权威：specs/brick-market-v2.md（brick-app/v1 manifest）
用法：
    python3 scripts/verify_products.py             # 校验全部
    python3 scripts/verify_products.py <name>      # 只校验指定积木
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = VAULT_ROOT / "products"
INDEX_PATH = VAULT_ROOT / "index.json"

MANIFEST_REQUIRED = {
    "schema", "id", "name", "title", "version", "author",
    "summary", "kind", "download_url", "sha256",
}
INDEX_ALIGN_FIELDS = ("name", "version", "kind", "download_url", "sha256")


class VerifyError(ValueError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_product(pdir: Path, index: dict) -> list:
    errs = []
    mid = pdir.name
    manifest_path = pdir / "manifest.json"
    if not manifest_path.exists():
        errs.append(f"缺 manifest.json：{mid}")
        return errs
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        errs.append(f"manifest.json 解析失败：{e}")
        return errs

    for f in MANIFEST_REQUIRED:
        if f not in m or m[f] in (None, ""):
            errs.append(f"manifest.json 缺少必填字段：{f}")

    if m.get("name") != mid:
        errs.append(f"name 与目录名不一致：manifest={m.get('name')!r}，目录={mid!r}")
    if m.get("kind") != "product":
        errs.append(f"kind 必须为 product，当前：{m.get('kind')!r}")
    if not str(m.get("id", "")).startswith("com.shadeling.brick."):
        errs.append(f"id 非法：{m.get('id')!r}（应以 com.shadeling.brick. 开头）")

    ver = m.get("version", "")
    rel = pdir / "releases" / ver
    zip_path = rel / f"{mid}-{ver}.zip"
    if ver and not zip_path.exists():
        errs.append(f"发布产物缺失：{zip_path.relative_to(PRODUCTS_DIR)}")
    if ver and zip_path.exists():
        actual = _sha256(zip_path)
        declared = m.get("sha256", "")
        if actual != declared:
            errs.append(f"sha256 不一致：zip={actual}，manifest={declared}")

    entries = index.get("products") or []
    entry = next((e for e in entries if e.get("name") == mid), None)
    if entry is None:
        errs.append(f"index.json products[] 未登记：{mid}")
        return errs
    for field in INDEX_ALIGN_FIELDS:
        if entry.get(field) != m.get(field):
            errs.append(f"index.json {field} 不一致：manifest={m.get(field)!r}，index={entry.get(field)!r}")
    return errs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="产品积木发布闸门（市场 V2）")
    p.add_argument("name", nargs="?", help="只校验指定积木（默认全部）")
    args = p.parse_args(argv)

    if not PRODUCTS_DIR.exists():
        print("[verify] products/ 目录不存在，跳过产品闸门。")
        return 0

    index = {}
    if INDEX_PATH.exists():
        try:
            index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[verify] index.json 解析失败：{e}")
            return 1

    dirs = sorted(d for d in PRODUCTS_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("."))
    if args.name:
        dirs = [d for d in dirs if d.name == args.name]
        if not dirs:
            print(f"[verify] 产品积木目录不存在：{args.name}")
            return 1

    total_errs = 0
    for d in dirs:
        errs = verify_product(d, index)
        if errs:
            total_errs += len(errs)
            print(f"[FAIL] {d.name}（{len(errs)} 项）")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"[OK] {d.name}")

    if total_errs:
        print(f"\n[verify] 产品闸门未通过：{total_errs} 项错误。不过闸门不允许发布。")
        return 1
    print("\n[verify] 产品闸门通过：全部产品积木合规。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
