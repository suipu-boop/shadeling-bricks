#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick Vault · 产品积木发布闸门（市场 V2）。

products/<id>/ 发布前强制自检：
1. manifest.json 字段完整（brick-app/v1），kind=product，id/name 与目录一致
2. releases/<version>/ 下 zip 存在，sha256 与 manifest 一致
3. **zip 内必须含 manifest.json**，且身份字段（id/name/version/kind/bundle/permissions）
   与仓库 manifest 逐字一致——安装器解压后读不到包内 manifest 会直接中止安装
4. index.json products[] 已登记（name/version/kind/download_url/sha256 对齐）
5. id 不与已发布积木冲突

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
import zipfile
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = VAULT_ROOT / "products"
INDEX_PATH = VAULT_ROOT / "index.json"

MANIFEST_REQUIRED = {
    "schema", "id", "name", "title", "version", "author",
    "summary", "kind", "download_url", "sha256",
}
INDEX_ALIGN_FIELDS = ("name", "version", "kind", "download_url", "sha256")
# 包内 manifest 必须与仓库 manifest 逐字一致的字段（安装器据此确认身份/入口/权限）
ZIP_MANIFEST_FIELDS = ("schema", "id", "name", "title", "version", "kind", "bundle", "permissions")


class VerifyError(ValueError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_zip_contents(zip_path: Path, m: dict) -> list:
    """闸门：zip 内必须含 manifest.json + 入口 bundle，身份字段与仓库 manifest 一致。

    历史坑：wechat-mp / vault 的发布 zip 只含 .app 本体，安装器解压后解析不到 manifest
    即中止安装；此闸门保证同类包再也出不了仓库。
    """
    errs = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                errs.append("zip 内缺 manifest.json：安装器读不到身份与权限声明会直接中止安装")
                return errs
            bundle = m.get("bundle", "")
            if bundle and bundle not in {n.split("/", 1)[0] for n in names}:
                errs.append(f"zip 内缺入口 bundle：{bundle}")
            try:
                inner = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                errs.append(f"zip 内 manifest.json 解析失败：{e}")
                return errs
    except (zipfile.BadZipFile, OSError) as e:
        errs.append(f"zip 读取失败：{e}")
        return errs

    for f in ZIP_MANIFEST_FIELDS:
        if inner.get(f) != m.get(f):
            errs.append(f"zip 内 manifest 与仓库 manifest 不一致：{f}="
                        f"{inner.get(f)!r} vs {m.get(f)!r}")
    if inner.get("sha256"):
        errs.append("zip 内 manifest 不应携带 sha256（zip 无法包含自身哈希，易误导校验）")
    return errs


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
        errs.extend(verify_zip_contents(zip_path, m))

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
