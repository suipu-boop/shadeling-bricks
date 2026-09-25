#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick Vault · 产品积木出包收尾（市场 V2）。

解决两类「长得对但装不上」的坑：

1. **zip 内缺 manifest.json**：安装器解压后要读包内 manifest 才能确认身份 / 入口 bundle /
   权限声明，缺了直接中止安装（实测 wechat-mp / vault 两只包曾因此装不上）。
   本脚本 `stage` 子命令把仓库侧 manifest 的身份字段暂存进 dist/，由 package_app.sh
   一并打进 zip。
2. **sha256 靠人手回填**：出包后要同步更新 `products/<id>/manifest.json` 与
   `index.json`，漏一处就会让校验闸门 / 安装期 sha256 校验失败。`finalize` 子命令
   一次性算哈希、写 .sha256、回填两处登记，并复核 zip 内容。

用法（通常由 products/<id>/source/package_app.sh 调用，不必手敲）：
    python3 scripts/pack_product.py stage    --product wechat-mp --out <dist>/manifest.json
    python3 scripts/pack_product.py finalize --product wechat-mp --version 1.0.0

设计约定：**包内 manifest 不携带 `sha256` / `download_url`**——二者是仓库侧发布元数据，
且 zip 无法包含自身的哈希（回填即失效）。安装器只读身份 / 权限字段，不依赖它们。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = VAULT_ROOT / "products"
INDEX_PATH = VAULT_ROOT / "index.json"

# 仓库侧发布元数据：不进包内 manifest（见模块 docstring）
RELEASE_META_FIELDS = ("sha256", "download_url")

# 包内 manifest 与仓库 manifest 必须逐字一致的字段
IDENTITY_FIELDS = ("schema", "id", "name", "title", "version", "kind", "bundle", "permissions")


class PackError(ValueError):
    """出包不合契约。"""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise PackError(f"读取/解析失败：{path}（{e}）") from e


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_path(product: str) -> Path:
    return PRODUCTS_DIR / product / "manifest.json"


def _rel(path: Path) -> str:
    """仓库内文件显示相对路径；仓库外（测试临时目录）显示绝对路径。"""
    try:
        return str(path.relative_to(VAULT_ROOT))
    except ValueError:
        return str(path)


def _release_paths(product: str, version: str):
    rel = PRODUCTS_DIR / product / "releases" / version
    zip_path = rel / f"{product}-{version}.zip"
    return rel, zip_path, Path(str(zip_path) + ".sha256")


def stage(product: str, out: Path) -> None:
    """把仓库 manifest 的身份字段暂存到 out（剥掉仓库侧发布元数据）。"""
    m = _read_json(_manifest_path(product))
    missing = [f for f in IDENTITY_FIELDS if not m.get(f) and f != "permissions"]
    if missing:
        raise PackError(f"manifest 缺必填字段：{', '.join(missing)}")
    if m.get("kind") != "product":
        raise PackError(f"kind 必须为 product，当前：{m.get('kind')!r}")
    if m.get("name") != product:
        raise PackError(f"manifest.name 与产品目录不一致：{m.get('name')!r} vs {product!r}")

    inner = {k: v for k, v in m.items() if k not in RELEASE_META_FIELDS}
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(out, inner)
    print(f"[stage] 包内 manifest：{out}")
    print(f"        id={inner.get('id')} version={inner.get('version')} "
          f"bundle={inner.get('bundle')} permissions={inner.get('permissions') or []}")


def _check_zip(zip_path: Path, m: dict, product: str) -> None:
    """复核 zip：必须含 manifest.json + 入口 bundle，且身份字段与仓库 manifest 一致。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise PackError(
                f"zip 内缺 manifest.json：{zip_path.name}（安装器会拒绝安装，闸门拦住不出包）")
        roots = {n.split("/", 1)[0] for n in names}
        bundle = m.get("bundle", "")
        if bundle and bundle not in roots:
            raise PackError(f"zip 内缺入口 bundle：{bundle}")
        try:
            inner = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise PackError(f"zip 内 manifest.json 解析失败：{e}") from e

    for f in IDENTITY_FIELDS:
        if inner.get(f) != m.get(f):
            raise PackError(f"zip 内 manifest 与仓库 manifest 不一致：{f}="
                            f"{inner.get(f)!r} vs {m.get(f)!r}")
    if inner.get("sha256"):
        raise PackError("zip 内 manifest 不应携带 sha256（zip 无法包含自身哈希）")


def finalize(product: str, version: str) -> None:
    """算 sha256 → 写 .sha256 → 回填 manifest.json 与 index.json → 复核。"""
    mpath = _manifest_path(product)
    m = _read_json(mpath)
    if m.get("version") != version:
        raise PackError(f"版本不一致：manifest.version={m.get('version')!r}，出包版本={version!r}")

    expected_url = (f"https://github.com/suipu-boop/shadeling-bricks/raw/main/"
                    f"products/{product}/releases/{version}/{product}-{version}.zip")
    if m.get("download_url") != expected_url:
        raise PackError(f"download_url 与发布路径不符（下载必 404）：\n"
                        f"    manifest: {m.get('download_url')}\n"
                        f"    期望    : {expected_url}")

    rel_dir, zip_path, sha_path = _release_paths(product, version)
    if not zip_path.exists():
        raise PackError(f"发布产物不存在：{zip_path}")
    _check_zip(zip_path, m, product)

    digest = _sha256(zip_path)
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    m["sha256"] = digest
    _write_json(mpath, m)

    index = _read_json(INDEX_PATH) if INDEX_PATH.exists() else {}
    products = index.setdefault("products", [])
    entry = next((e for e in products if e.get("name") == product), None)
    if entry is None:
        entry = {"name": product}
        products.append(entry)
    entry.update({"name": product, "version": version, "kind": m.get("kind", "product"),
                  "download_url": m["download_url"], "sha256": digest})
    if "updated_at" in index:
        index["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(INDEX_PATH, index)

    print(f"[finalize] zip      : {_rel(zip_path)}")
    print(f"[finalize] sha256   : {digest}")
    print(f"[finalize] 已回填   : {_rel(mpath)} + {INDEX_PATH.name} products[]")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="产品积木出包收尾（市场 V2）")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("stage", help="暂存包内 manifest.json（剥掉发布元数据）")
    ps.add_argument("--product", required=True)
    ps.add_argument("--out", required=True, type=Path)

    pf = sub.add_parser("finalize", help="算 sha256 并回填 manifest.json / index.json")
    pf.add_argument("--product", required=True)
    pf.add_argument("--version", required=True)

    args = p.parse_args(argv)
    try:
        if args.cmd == "stage":
            stage(args.product, args.out)
        else:
            finalize(args.product, args.version)
    except PackError as e:
        print(f"[abort] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
