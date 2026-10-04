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
6. **声明式（`brick-app/v2`）三项扩展**（契约 §3.6-7，模板规格 §3 Phase 3）：
   - `ui.entry` 存在且在 zip 内可解析（§2.2 文档结构 / §2.3 节点模型 / §2.7 静态约束）
   - 无裸弹层调用：弹层必须写成 `overlay` 节点 + 子类型，不得直接以弹层类型作节点
   - `logic.entry` 已登记哈希或签名（`manifest.logic.sha256` 或 `manifest.logic.signature`）

契约权威：specs/brick-market-v2.md（brick-app/v1 manifest）、
specs/Shadeling积木声明式UI架构设计与契约-v0.1.md §2 / §3.6 / §7.4
用法：
    python3 scripts/verify_products.py             # 校验全部
    python3 scripts/verify_products.py <name>      # 只校验指定积木
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
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
ZIP_MANIFEST_FIELDS = ("schema", "id", "name", "title", "version", "kind", "bundle", "permissions",
                       "nav", "ui", "logic")

# —— C4 声明式（v2）发布闸门常量（契约 §2.2~§2.7 / §3.3 / §3.6-7）——
SCHEMA_V2 = "brick-app/v2"
UI_SCHEMA = "shadeling-ui/1"
UI_MAX_DEPTH = 16          # §2.7：节点嵌套深度上限（根为 1）
UI_MAX_NODES = 2000        # §2.7：单帧节点数上限
# §2.5 组件白名单 + §2.3 布局原语（grid / scroll / spacer）
UI_NODE_TYPES = {"container", "text", "button", "list", "card", "form", "icon",
                 "progress", "overlay", "image", "grid", "scroll", "spacer"}
# §2.3：仅容器类节点可携带 children
UI_LEAF_TYPES = {"text", "button", "icon", "progress", "image", "spacer"}
# §2.5-9：弹层子类型（必须挂在 overlay 节点上）
OVERLAY_SUBTYPES = {"sheet", "dialog", "banner", "toast"}
# 裸弹层：直接以弹层类型作节点 type（含系统弹层别名），一律拦截
BARE_OVERLAY_TYPES = {"sheet", "dialog", "banner", "toast", "alert", "confirm",
                      "confirmation_dialog", "popover", "modal", "action_sheet", "hud"}
NODE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
# 签名登记口径（契约仅要求「已签名或哈希登记」，未定格式；此处取 vault 统一前缀）
SIGNATURE_PREFIX = "shadeling-sig/v1:"


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


# ——————————————————————————————————————————————————————————————
# C4：声明式（v2）发布闸门三项扩展（契约 §3.6-7 / §7.4 验收 6）
#   ① ui.entry 存在且可解析  ② 无裸弹层调用  ③ logic.entry 已签名或哈希登记
# 规则表口径同 §2.2 / §2.3 / §2.5 / §2.7；v1（bundle 形态）在兼容期（§3.5）不适用。
# ——————————————————————————————————————————————————————————————

def verify_ui_document(doc) -> list:
    """校验 UI 文档可解析性与静态约束（§2.2 / §2.3 / §2.7），并拦截裸弹层（②）。

    错误前缀区分两条判据：结构问题统一 "UI 文档"，裸弹层为 "裸弹层调用"。
    """
    errs = []
    if not isinstance(doc, dict):
        return ["UI 文档必须是 JSON 对象（§2.2）"]
    if doc.get("schema") != UI_SCHEMA:
        errs.append(f"UI 文档 schema 必须为 {UI_SCHEMA}，当前：{doc.get('schema')!r}")
    if not isinstance(doc.get("version"), int) or isinstance(doc.get("version"), bool):
        errs.append(f"UI 文档 version 必须为整数，当前：{doc.get('version')!r}")
    root = doc.get("root")
    if not isinstance(root, dict):
        errs.append("UI 文档缺 root 节点（§2.2：root 必填且为容器类节点）")
        return errs
    if root.get("type") not in UI_NODE_TYPES - UI_LEAF_TYPES:
        errs.append(f"UI 文档 root 必须为容器类节点，当前：{root.get('type')!r}")
    state = {"nodes": 0, "overflow": False}
    _walk_ui_node(root, 1, "root", state, errs)
    return errs


def _walk_ui_node(node, depth: int, path: str, state: dict, errs: list) -> None:
    """深度优先遍历节点树；超限只记一次，避免刷屏。"""
    if state["overflow"]:
        return
    if not isinstance(node, dict):
        errs.append(f"UI 节点必须是对象：{path}")
        return
    state["nodes"] += 1
    if state["nodes"] > UI_MAX_NODES:
        state["overflow"] = True
        errs.append(f"UI 文档节点数超上限 {UI_MAX_NODES}（§2.7）")
        return
    if depth > UI_MAX_DEPTH:
        state["overflow"] = True
        errs.append(f"UI 文档嵌套深度超上限 {UI_MAX_DEPTH}（§2.7）：{path}")
        return

    ntype = node.get("type")
    if ntype in BARE_OVERLAY_TYPES:
        errs.append(f"裸弹层调用：{path} 的 type={ntype!r} 非法，弹层必须写成 overlay 节点 "
                    f"（overlay.subtype ∈ {sorted(OVERLAY_SUBTYPES)}，§2.5-9）")
    elif ntype not in UI_NODE_TYPES:
        errs.append(f"UI 节点类型不在白名单：{path} 的 type={ntype!r}（§2.3：未知类型整帧拒绝）")

    nid = node.get("id")
    if not isinstance(nid, str) or not NODE_ID_RE.match(nid):
        errs.append(f"UI 节点 id 非法：{path} 的 id={nid!r}（须匹配 ^[a-z][a-z0-9_]{{0,63}}$）")

    if ntype == "overlay":
        props = node.get("props") if isinstance(node.get("props"), dict) else {}
        sub = node.get("subtype", props.get("subtype"))
        if sub not in OVERLAY_SUBTYPES:
            errs.append(f"overlay 节点子类型非法：{path} 的 subtype={sub!r}"
                        f"（须为 {sorted(OVERLAY_SUBTYPES)} 之一，§2.5-9）")

    children = node.get("children")
    if children is None:
        return
    if not isinstance(children, list):
        errs.append(f"UI 节点 children 必须为数组：{path}")
        return
    if ntype in UI_LEAF_TYPES:
        errs.append(f"叶子节点不得携带 children：{path}（type={ntype!r}，§2.3）")
        return
    for i, child in enumerate(children):
        _walk_ui_node(child, depth + 1, f"{path}.children[{i}]", state, errs)


def verify_ui_entry(zf: zipfile.ZipFile, m: dict) -> list:
    """判据①+②：ui.entry 存在且可解析（含裸弹层拦截）。"""
    ui = m.get("ui")
    if not isinstance(ui, dict):
        return ["manifest 缺 ui 段：v2 产品必须声明 UI 入口（§3.3）"]
    entry = ui.get("entry")
    if not isinstance(entry, str) or not entry:
        return ["manifest 缺 ui.entry（§3.3：首帧 UI 文档路径必填）"]
    if entry.startswith("/") or ".." in Path(entry).parts:
        return [f"ui.entry 路径非法（禁止绝对路径与 `..` 逃逸）：{entry!r}"]
    if entry not in set(zf.namelist()):
        return [f"zip 内缺 UI 入口：{entry}"]
    try:
        doc = json.loads(zf.read(entry).decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"UI 入口不可解析（{entry}）：{e}"]
    return verify_ui_document(doc)


def verify_logic_entry(zf: zipfile.ZipFile, m: dict) -> list:
    """判据③：logic.entry 存在于包内，且已登记哈希（sha256）或签名（signature）。"""
    logic = m.get("logic")
    if not isinstance(logic, dict):
        return ["manifest 缺 logic 段：v2 产品必须声明逻辑入口（§3.3）"]
    entry = logic.get("entry")
    if not isinstance(entry, str) or not entry:
        return ["manifest 缺 logic.entry（§3.3：逻辑进程入口必填）"]
    errs = []
    if entry.startswith("/") or ".." in Path(entry).parts:
        errs.append(f"logic.entry 路径非法（禁止绝对路径与 `..` 逃逸）：{entry!r}")
    payload = None
    if entry in set(zf.namelist()):
        try:
            payload = zf.read(entry)
        except OSError as e:  # pragma: no cover - 读 zip 成员失败
            errs.append(f"logic.entry 读取失败：{entry}（{e}）")
    else:
        errs.append(f"zip 内缺 logic.entry：{entry}")

    digest = logic.get("sha256") or m.get("logic_sha256")
    signature = logic.get("signature")
    if not digest and not signature:
        errs.append("logic.entry 未登记哈希或签名：需在 manifest.logic.sha256（推荐，64 位十六进制）"
                    "或 manifest.logic.signature（前缀 shadeling-sig/v1:）登记（§3.6-7）")
    if digest:
        if not SHA256_RE.match(str(digest)):
            errs.append(f"logic.sha256 必须为 64 位十六进制，当前：{digest!r}")
        elif payload is not None:
            actual = hashlib.sha256(payload).hexdigest()
            if actual != str(digest).lower():
                errs.append(f"logic.entry 哈希不一致：zip={actual}，manifest={digest}")
    if signature and not str(signature).startswith(SIGNATURE_PREFIX):
        errs.append(f"logic.signature 格式非法（须以 {SIGNATURE_PREFIX} 开头）：{str(signature)[:32]!r}…")
    return errs


def verify_v2_declarative_gates(zip_path: Path, m: dict) -> list:
    """闸门三项总入口；非声明式（v1 bundle 形态）按 §3.5 兼容期直接放行。"""
    is_v2 = (m.get("schema") == SCHEMA_V2
             or isinstance(m.get("ui"), dict) or isinstance(m.get("logic"), dict))
    if not is_v2:
        return []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return verify_ui_entry(zf, m) + verify_logic_entry(zf, m)
    except (zipfile.BadZipFile, OSError):
        # zip 自身不可读已由 verify_zip_contents 报出，此处避免重复报错
        return []


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
        errs.extend(verify_v2_declarative_gates(zip_path, m))

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
