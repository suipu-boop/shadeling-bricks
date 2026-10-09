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
import time
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_ui_doc  # noqa: E402  # 打包闸门：装机期同源规则表（避免装机才炸 4303）

VAULT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = VAULT_ROOT / "products"
INDEX_PATH = VAULT_ROOT / "index.json"

# 仓库侧发布元数据：不进包内 manifest（见模块 docstring）
RELEASE_META_FIELDS = ("sha256", "download_url")

# 包内 manifest 与仓库 manifest 必须逐字一致的字段
# - v1（bundle 形态）：顶层 bundle + id
# - v2 声明式（契约 §3.3 / §3.6-1）：无 bundle / id，改 brick_id + nav / ui / logic 三段
IDENTITY_FIELDS_V1 = ("schema", "id", "name", "title", "version", "kind", "bundle", "permissions")
IDENTITY_FIELDS_V2 = ("schema", "brick_id", "name", "title", "version", "kind",
                      "permissions", "nav", "ui", "logic")
SCHEMA_V2 = "brick-app/v2"


def identity_fields(m: dict) -> tuple:
    """按 schema 分流身份字段集合（v2 声明式与服务端/宿主判据同源）。"""
    return IDENTITY_FIELDS_V2 if m.get("schema") == SCHEMA_V2 else IDENTITY_FIELDS_V1


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
    fields = identity_fields(m)
    missing = [f for f in fields if not m.get(f) and f != "permissions"]
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
    """复核 zip：必须含 manifest.json + 入口，且身份字段与仓库 manifest 一致。

    - v1（bundle 形态）：要求 zip 内含入口 `.app` 目录（与旧口径逐字一致）；
    - v2 声明式（`brick-app/v2`）：无 bundle，改校验 `ui.entry` / `logic.entry` 在包内
      （与宿主 `BrickManifestV2.checkEntry`、发布闸门 `verify_ui_entry` /
      `verify_logic_entry` 判据同源，§3.3 / §3.6-7）。
    """
    is_v2 = m.get("schema") == SCHEMA_V2
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise PackError(
                f"zip 内缺 manifest.json：{zip_path.name}（安装器会拒绝安装，闸门拦住不出包）")
        if is_v2:
            ui = m.get("ui") if isinstance(m.get("ui"), dict) else {}
            logic = m.get("logic") if isinstance(m.get("logic"), dict) else {}
            for label, rel in (("ui.entry", ui.get("entry")), ("logic.entry", logic.get("entry"))):
                if not rel:
                    raise PackError(f"v2 manifest 缺 {label}（契约 §3.3）")
                if str(rel).startswith("/") or ".." in Path(str(rel)).parts:
                    raise PackError(f"{label} 路径非法（禁止绝对路径与 `..` 逃逸）：{rel!r}")
                if rel not in names:
                    raise PackError(f"zip 内缺 {label}：{rel}（安装器会拒装）")
        else:
            bundle = m.get("bundle", "")
            if bundle and bundle not in {n.split("/", 1)[0] for n in names}:
                raise PackError(f"zip 内缺入口 bundle：{bundle}")
        try:
            inner = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise PackError(f"zip 内 manifest.json 解析失败：{e}") from e

    for f in identity_fields(m):
        if inner.get(f) != m.get(f):
            raise PackError(f"zip 内 manifest 与仓库 manifest 不一致：{f}="
                            f"{inner.get(f)!r} vs {m.get(f)!r}")
    if inner.get("sha256"):
        raise PackError("zip 内 manifest 不应携带 sha256（zip 无法包含自身哈希）")


def _gate_ui_document(pdir: Path, entry: str) -> None:
    """打包闸门：ui 文档先过同源规则表（scripts/verify_ui_doc.py），不过即拒出包。

    此前该口径只在装机期（宿主 BrickInstallGate → UIDocumentValidator）生效，
    带病内容能出包、装机才炸 4303；本闸门把失败前移（契约 §7.5 / §2.4 布尔位）。
    """
    if not entry:
        raise PackError("v2 manifest 缺 ui.entry（契约 §3.3）")
    src = pdir / entry
    if not src.is_file():
        raise PackError(f"ui.entry 在仓库内不存在：{src}")
    try:
        document = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise PackError(f"ui.entry 解析失败（{entry}）：{exc}") from exc
    issues = verify_ui_doc.Issues()
    verify_ui_doc.verify_document(document, issues)
    if issues:
        detail = "\n".join("  - " + item for item in issues.items)
        raise PackError(f"ui.entry 未过规则表校验（{entry}）：\n{detail}")
    print(f"[gate] ui 文档通过规则表校验：{entry}")


def pack(product: str, version: str, out: Path | None = None) -> None:
    """v2 声明式产品出包：zip 根 = manifest.json + ui/ + logic/（无 `.app` bundle）。

    与 v1 的 `source/package_app.sh` 并列：v2 不再有 bundle，宿主安装器按 `ui.entry` /
    `logic.entry` 在包内落位（契约 §3.3 / §3.5）。排除 `__pycache__` / `.pyc` / `.DS_Store`；
    `logic.entry` 以可执行位（0755）入包，兼容宿主 `runtime=executable` / `python3` / `node` 三种口径
    （后两者执行位非必需，统一 0755 不影响：底座以 `[解释器, entry]` 启动，入口只需可读）。
    """
    m = _read_json(_manifest_path(product))
    if m.get("schema") != SCHEMA_V2:
        raise PackError(f"{product} 不是 {SCHEMA_V2}（v1 形态请走 source/package_app.sh）")
    if m.get("version") != version:
        raise PackError(f"版本不一致：manifest.version={m.get('version')!r}，出包版本={version!r}")

    pdir = PRODUCTS_DIR / product
    ui = m.get("ui") if isinstance(m.get("ui"), dict) else {}
    logic = m.get("logic") if isinstance(m.get("logic"), dict) else {}
    sections = (("ui", ui.get("entry")), ("logic", logic.get("entry")))
    for label, rel in sections:
        if not rel:
            raise PackError(f"v2 manifest 缺 {label}.entry（契约 §3.3）")

    if out is None:
        _, out, _ = _release_paths(product, version)
    out.parent.mkdir(parents=True, exist_ok=True)

    _gate_ui_document(pdir, ui.get("entry"))

    skip_dirs = {"__pycache__", ".git"}
    skip_files = {".DS_Store"}
    inner = {k: v for k, v in m.items() if k not in RELEASE_META_FIELDS}

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",
                    json.dumps(inner, ensure_ascii=False, indent=2) + "\n")
        for label, rel in sections:
            src = pdir / rel
            if src.is_file():
                targets = [(src, str(rel))]
            elif src.is_dir():
                targets = [(f, f.relative_to(pdir).as_posix()) for f in sorted(src.rglob("*"))
                           if f.is_file()
                           and not any(part in skip_dirs for part in f.relative_to(pdir).parts)
                           and f.name not in skip_files]
            else:
                raise PackError(f"{label}.entry 在仓库内不存在：{src}")
            if not targets:
                raise PackError(f"{label}.entry 无可打包文件：{rel}")
            for f, arc in targets:
                mode = 0o755 if arc == logic.get("entry") else 0o644
                info = zipfile.ZipInfo(arc, date_time=time.localtime(f.stat().st_mtime)[:6])
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, f.read_bytes())

    print(f"[pack] 已出包：{_rel(out)}")
    for label, rel in sections:
        print(f"       段 {label}：{rel}")


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

    pp = sub.add_parser("pack", help="v2 声明式产品出包（manifest.json + ui/ + logic/）")
    pp.add_argument("--product", required=True)
    pp.add_argument("--version", required=True)
    pp.add_argument("--out", type=Path, default=None,
                    help="输出 zip 路径（默认落 releases/<version>/）")

    args = p.parse_args(argv)
    try:
        if args.cmd == "stage":
            stage(args.product, args.out)
        elif args.cmd == "pack":
            pack(args.product, args.version, args.out)
        else:
            finalize(args.product, args.version)
    except PackError as e:
        print(f"[abort] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
