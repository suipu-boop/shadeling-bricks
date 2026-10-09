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
6. **声明式（`brick-app/v2`）扩展**（契约 §3.3 / §3.5 / §3.6，模板规格 §3 Phase 3）：
   - 三段硬卡点：`nav` / `ui` / `logic` 齐备（缺段或「存在但不是对象」即拒发布，§3.6-1）
   - `ui.entry` 存在且在 zip 内可解析（§2.2 文档结构 / §2.3 节点模型 / §2.7 静态约束）
   - 无裸弹层调用：弹层必须写成 `overlay` 节点 + 子类型，不得直接以弹层类型作节点
   - `logic.entry` 已登记哈希或签名（`manifest.logic.sha256` 或 `manifest.logic.signature`）
   - `logic.env` 键白名单（显式正列举，首批为空集 = `logic.env` 必须为空对象，§3.6-5）
   非 `brick-app/v2`（v1 / 未标 schema 的历史包）按 §3.5 兼容期不适用本组检查。
7. **版本一致性闸门（E1.1）**：`manifest.version` 必须与仓库 `source/Info.plist`、
   发布 zip 内入口 bundle 的 `Contents/Info.plist` 的 `CFBundleShortVersionString` 一致
   （历史坑：wechat-mp 的 Info.plist 停在 1.0.0 而 manifest 已到 1.1.0，装出来的版本对不上）
   适用口径：仅 v1（声明了 `bundle` 的 app 形态）产品；v2 声明式积木不发布 .app，不校验源码 plist
8. **权限段台账闸门（E1.1）**：`manifest.permission_risks`（若声明）须与 `permissions` 双向一致：
   declared 项必须在 `permissions` 内，pending / resolved 项必须在 `permissions` 外，
   且 `level ∈ {low, mid, high, app-level}`、`status ∈ {declared, pending, resolved}`
9. **模板 Phase 3 源码闸门**（规格 `specs/积木规范化模板-v0.1.md` §Phase 3）：
   对声明式（`brick-app/v2`）产品的 `source/` 源码做三项静态检查——
   `source/Package.swift` 必须含 BrickUIKit 依赖；业务源码禁颜色字面量
   （`Color(red:` / `NSColor(red:` / `#colorLiteral(` / `Color(hex: …)` / `Color("#rrggbb")`；
   BrickUIKit 自身不在本仓、不扫）；业务源码禁裸弹层 `.alert(` / `.sheet(` /
   `.confirmationDialog(`（须走 `brick*` 封装）。
   既存产物不误伤：`SOURCE_GATE_EXEMPT` 登记的历史遗留违规项只记录（`[warn]`）不判错，
   待该源码下次改动时收敛；无 `source/` 或无 `Package.swift` 的形态按分流跳过。

契约权威：specs/brick-market-v2.md（brick-app/v1 manifest）、
specs/Shadeling积木声明式UI架构设计与契约-v1.0.md §2 / §3.6 / §7.4
用法：
    python3 scripts/verify_products.py             # 校验全部
    python3 scripts/verify_products.py <name>      # 只校验指定积木
"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import sys
import zipfile
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = VAULT_ROOT / "products"
INDEX_PATH = VAULT_ROOT / "index.json"

MANIFEST_REQUIRED = {
    "schema", "name", "title", "version", "author",
    "summary", "kind", "download_url", "sha256",
}
# 身份键按 schema 分流（契约 §3.3 / §3.4）：v1 顶层 `id`；v2 改 `brick_id`
IDENTITY_KEY_V1 = "id"
IDENTITY_KEY_V2 = "brick_id"
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
# 签名登记口径（契约 §3.3 登记字段，2026-10-06 owner 拍板取 C；此处取 vault 统一前缀）
SIGNATURE_PREFIX = "shadeling-sig/v1:"
# §3.6-1（2026-10-06 owner 拍板 A）：brick-app/v2 强制 nav / ui / logic 三段齐备
REQUIRED_SECTIONS = ("nav", "ui", "logic")
# §3.3 / §3.6-5（2026-10-06 owner 拍板 B）：logic.env 显式正列举白名单，首批为空集
ALLOWED_LOGIC_ENV_KEYS: frozenset = frozenset()

# —— E1.1 闸门常量：版本一致性 + 权限段台账（permission_risks）——
PLIST_VERSION_KEY = "CFBundleShortVersionString"    # 与 manifest.version 对齐的 plist 键
RISK_LEVELS = ("low", "mid", "high", "app-level")   # 级别口径同宿主 BrickPermission.level
RISK_STATUSES = ("declared", "pending", "resolved")  # 落地状态：已声明 / 待落地 / 核查后无需声明

# —— 模板 Phase 3 源码闸门（规格 v0.1 §Phase 3 / §Phase 4 第 4 条）——
# 适用形态：声明式（brick-app/v2）产品 + 仓库内存在 source/ 源码目录；v1（bundle 形态）
# 按 §3.5 兼容期不适用；纯声明式（无源码）按形态分流跳过。BrickUIKit 依赖走跨仓相对路径，
# 不在本仓、不属于产品业务源码，因此颜色字面量白名单即"只扫产品自身 Sources"。
SOURCE_REQUIRED_DEP = "BrickUIKit"
# 颜色字面量（业务源码禁止直接构造颜色，须走 BrickUIKit Design.ColorPalette 令牌）
COLOR_LITERAL_RES = (
    ("Color(red:", re.compile(r"\bColor\s*\(\s*red\s*:")),
    ("NSColor(red:", re.compile(r"\bNSColor\s*\(\s*red\s*:")),
    ("#colorLiteral(", re.compile(r"#colorLiteral\s*\(")),
    ("Color(hex:)/NSColor(hex:)", re.compile(r"\b(?:Color|NSColor)\s*\(\s*hex\s*:")),
    ('Color("#rrggbb")', re.compile(r"\b(?:Color|NSColor)\s*\(\s*\"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})\"")),
)
# 裸弹层调用（须走 brick* 封装：.brickSheet / .brickAlert / .brickConfirm）
BARE_PRESENTATION_RE = re.compile(r"\.(alert|sheet|confirmationDialog)\s*\(")
# 源码闸门豁免台账（只记录不误伤既有产物）：产品 → 规则键集合（空集 = 全量判错）。
# 用途：早期源码早于模板收敛，拿新规则回溯追责会让历史产物"天生不合规"；此处登记为
# 待收敛项，闸门对其打印 [warn] 但不计入错误，待该源码下次改动时随模板一并收敛。
SOURCE_GATE_EXEMPT: dict = {
    "vault": {
        "rules": {"color_literal"},
        "warn": "[源码闸门·豁免] VaultStyle.swift 仍含 Color(red:) 颜色字面量"
                "（模板 Phase 3 收敛前遗留），登记为待收敛项：只记录不计错，"
                "待 vault 源码下次改动时改用 BrickUIKit Design.ColorPalette",
    },
}


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
                    f"（overlay.kind ∈ {sorted(OVERLAY_SUBTYPES)}，§2.5-9）")
    elif ntype not in UI_NODE_TYPES:
        errs.append(f"UI 节点类型不在白名单：{path} 的 type={ntype!r}（§2.3：未知类型整帧拒绝）")

    nid = node.get("id")
    if not isinstance(nid, str) or not NODE_ID_RE.match(nid):
        errs.append(f"UI 节点 id 非法：{path} 的 id={nid!r}（须匹配 ^[a-z][a-z0-9_]{{0,63}}$）")

    if ntype == "overlay":
        props = node.get("props") if isinstance(node.get("props"), dict) else {}
        # 载体口径统一为 props.kind（契约 §2.5-9；与 Swift UIDocumentValidator.validateOverlay 同源）。
        # 顶层 `subtype` 为历史写法，不再作为判据（遗留包内出现不报错）。
        kind = props.get("kind")
        if kind is None:
            errs.append(f"overlay 节点缺子类载体 props.kind：{path}"
                        f"（须为 {sorted(OVERLAY_SUBTYPES)} 之一，§2.5-9）")
        elif kind not in OVERLAY_SUBTYPES:
            errs.append(f"overlay 节点子类型非法：{path} 的 props.kind={kind!r}"
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
    """判据③：logic.entry 存在于包内，且已登记哈希（sha256）或签名（signature）（§3.3）。"""
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


def verify_required_sections(m: dict) -> list:
    """闸门①：`brick-app/v2` 强制 `nav` / `ui` / `logic` 三段齐备（§3.6-1）。

    与宿主 `BrickInstallGate.validateRequiredSections` 同源：缺段（含「段存在但不是对象」）
    即拒装 / 拒发布；v1（含未标 schema 的历史包）按 §3.5 兼容期不适用。
    """
    if m.get("schema") != SCHEMA_V2:
        return []
    errs = []
    for key in REQUIRED_SECTIONS:
        value = m.get(key)
        if isinstance(value, dict):
            continue
        mark = "整段缺失" if value is None else "存在但不是对象"
        errs.append(f"manifest 缺 {key} 段（{mark}）：{SCHEMA_V2} 强制 nav / ui / logic "
                    f"三段齐备，缺一不可（§3.6-1）")
    return errs


def verify_logic_env(m: dict) -> list:
    """闸门④：`logic.env` 键白名单（§3.3 / §3.6-5，显式正列举，首批为空集）。"""
    logic = m.get("logic")
    if not isinstance(logic, dict):
        return []  # 缺 logic 段由 verify_required_sections 报出，此处不重复
    env = logic.get("env")
    if env is None:
        return []
    if not isinstance(env, dict):
        return [f"logic.env 必须是对象，当前：{type(env).__name__}（§3.3）"]
    unknown = sorted(k for k in env if k not in ALLOWED_LOGIC_ENV_KEYS)
    if not unknown:
        return []
    return [f"logic.env 存在未登记键：{unknown}（白名单为显式正列举、当前为空集 = "
            f"logic.env 必须为空对象；放行具体键须先做「底座 ↔ 契约 §3.3」同步登记，"
            f"禁止按前缀或通配放行，§3.6-5）"]


def verify_v2_declarative_gates(zip_path: Path, m: dict) -> list:
    """闸门总入口；非声明式（v1 bundle 形态）按 §3.5 兼容期直接放行。

    顺序与宿主安装流程同序：先三段早检（§3.6-1，缺段即返回，避免被字段级文案淹没），
    再 `logic.env` 白名单，最后包内 `ui.entry` / `logic.entry` 检查。
    """
    is_v2 = (m.get("schema") == SCHEMA_V2
             or isinstance(m.get("ui"), dict) or isinstance(m.get("logic"), dict))
    if not is_v2:
        return []
    errs = verify_required_sections(m)
    if errs:
        return errs
    errs = verify_logic_env(m)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return errs + verify_ui_entry(zf, m) + verify_logic_entry(zf, m)
    except (zipfile.BadZipFile, OSError):
        # zip 自身不可读已由 verify_zip_contents 报出，此处避免重复报错
        return errs


def _plist_short_version(data: bytes):
    """取 Info.plist 的 CFBundleShortVersionString；解析失败抛 VerifyError，取不到版本号返回 None。"""
    try:
        pl = plistlib.loads(data)
    except Exception as e:  # plistlib 异常类型随内容而异（XML / 二进制 / 编码）
        raise VerifyError(f"Info.plist 解析失败：{e}") from e
    value = pl.get(PLIST_VERSION_KEY) if isinstance(pl, dict) else None
    return value if isinstance(value, str) and value else None


def verify_version_consistency(pdir: Path, m: dict, zip_path: Path) -> list:
    """闸门（E1.1）：`manifest.version` 必须与各处 Info.plist 的 CFBundleShortVersionString 一致。

    覆盖两处：仓库源码 `source/Info.plist`（出包输入）与发布 zip 内入口 bundle 的
    `Contents/Info.plist`（用户实际装到的版本）。历史坑：wechat-mp 的 Info.plist 长期停在
    1.0.0 而 manifest 已到 1.1.0，安装后系统「关于」版本与市场登记版本对不上。
    口径（2026-10-09 扩展）：① v1（声明了 `bundle` 的 app 形态）：`source/Info.plist` 即出包输入，
    与 zip 内入口 bundle 一并核对；② v2（声明式）但仓库仍留 `source/Info.plist` 的「源码形态」：
    plist 虽不在发布物内，但版本号长期脱钩会误导排查（历史坑见上），故一并核对。
    不存在 plist 的产品（纯声明式）直接跳过；存在但取不到版本号即报错。
    """
    errs = []
    ver = m.get("version") or ""

    src = pdir / "source" / "Info.plist"
    if src.exists() and (m.get("bundle") or m.get("schema") == SCHEMA_V2):
        try:
            got = _plist_short_version(src.read_bytes())
        except VerifyError as e:
            errs.append(f"source/Info.plist 无法核对版本：{e}")
        else:
            if got is None:
                errs.append(f"source/Info.plist 缺 {PLIST_VERSION_KEY}，无法与 manifest 版本核对")
            elif got != ver:
                errs.append(f"版本不一致：manifest.version={ver!r}，"
                            f"source/Info.plist {PLIST_VERSION_KEY}={got!r}")

    bundle = m.get("bundle") or ""
    if bundle:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                member = f"{bundle}/Contents/Info.plist"
                if member in set(zf.namelist()):
                    try:
                        got = _plist_short_version(zf.read(member))
                    except VerifyError as e:
                        errs.append(f"zip 内 {member} 无法核对版本：{e}")
                    else:
                        if got is None:
                            errs.append(f"zip 内 {member} 缺 {PLIST_VERSION_KEY}")
                        elif got != ver:
                            errs.append(f"版本不一致：manifest.version={ver!r}，"
                                        f"zip 内 {member} {PLIST_VERSION_KEY}={got!r}")
        except (zipfile.BadZipFile, OSError):
            pass  # zip 不可读已由 verify_zip_contents 报出，此处不重复报错
    return errs


def verify_permission_risks(m: dict) -> list:
    """闸门（E1.1）：权限段台账 `permission_risks` 与 `permissions` 双向一致。

    台账为 E1.1 引入的权限清单（逐项标风险级别 + 落地状态），供 Phase E 迁移期对照；
    未声明该键的产品跳过本闸门。级别 / 状态口径见盘点报告 §4 与宿主 `BrickPermission.level`。
    """
    rows = m.get("permission_risks")
    if rows is None:
        return []
    if not isinstance(rows, list):
        return [f"permission_risks 必须是数组，当前：{type(rows).__name__}"]

    errs = []
    perms = [p for p in (m.get("permissions") or []) if isinstance(p, str)]
    seen: dict = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errs.append(f"permission_risks[{i}] 必须是对象")
            continue
        name = row.get("permission")
        if not isinstance(name, str) or not name:
            errs.append(f"permission_risks[{i}] 缺 permission（权限名 / 待评审能力名）")
            continue
        if name in seen:
            errs.append(f"permission_risks 重复登记：{name}（第 {seen[name]} 项与第 {i} 项）")
            continue
        seen[name] = i
        level, status = row.get("level"), row.get("status")
        if level not in RISK_LEVELS:
            errs.append(f"permission_risks[{name}] level 非法：{level!r}"
                        f"（须为 {list(RISK_LEVELS)} 之一）")
        if status not in RISK_STATUSES:
            errs.append(f"permission_risks[{name}] status 非法：{status!r}"
                        f"（须为 {list(RISK_STATUSES)} 之一）")
            continue
        declared = name in perms
        if status == "declared" and not declared:
            errs.append(f"permission_risks[{name}] 标 declared 但未写入 permissions（台账与声明脱钩）")
        elif status != "declared" and declared:
            errs.append(f"permission_risks[{name}] 标 {status} 却出现在 permissions 里"
                        f"（pending / resolved 项不得声明；未知 agent.* / ui.* 等会被安装期未知值闸门拒装）")
    for p in perms:
        if p not in seen:
            errs.append(f"permissions 内的 {p!r} 未在 permission_risks 登记（E1.1 要求逐项标风险级别）")
    return errs


def _product_swift_sources(pdir: Path) -> list:
    """产品自身业务源码：`source/**/*.swift`，排除 `.build` 构建产物与 `Package.swift`。

    BrickUIKit 走跨仓相对路径依赖、不在本仓，天然落在扫描范围外（= 规格里"白名单：
    BrickUIKit 自身"的落地方式）。
    """
    out = []
    for f in sorted((pdir / "source").rglob("*.swift")):
        if ".build" in f.parts or f.name == "Package.swift":
            continue
        out.append(f)
    return out


def verify_source_gates(pdir: Path, m: dict) -> list:
    """闸门（模板 Phase 3 / 规格 v0.1 §Phase 3）：声明式产品 source 侧三项源码静态检查。

    ① `source/Package.swift` 必须含 BrickUIKit 依赖；② 业务源码禁颜色字面量；
    ③ 业务源码禁裸弹层 `.alert(` / `.sheet(` / `.confirmationDialog(`（须走 `brick*` 封装）。

    形态分流：仅 `brick-app/v2` 且仓库内存在 `source/` 的产品适用；v1 按 §3.5 兼容期跳过，
    无源码的纯声明式产品跳过。既存产物不误伤：`pdir.name` 在 SOURCE_GATE_EXEMPT 登记的
    规则，命中时只打印 `[warn]` 记录、不计入错误，避免拿新规则回溯追责历史产物。
    """
    if m.get("schema") != SCHEMA_V2:
        return []  # v1（bundle 形态）在兼容期（§3.5）不适用本组检查
    pid = pdir.name
    src_dir = pdir / "source"
    if not src_dir.is_dir():
        print(f"[skip] {pid}：无 source/ 源码目录（纯声明式形态），源码闸门不适用")
        return []

    errs = []
    pkg = src_dir / "Package.swift"
    if not pkg.exists():
        errs.append("源码闸门：source/Package.swift 缺失（模板 Phase 3：产品工程须携带 SPM 清单）")
    else:
        text = pkg.read_text(encoding="utf-8", errors="replace")
        if SOURCE_REQUIRED_DEP not in text:
            errs.append(f"源码闸门：source/Package.swift 未含 {SOURCE_REQUIRED_DEP} 依赖"
                        f"（模板 Phase 3 第 1 条：产品必须依赖 BrickUIKit）")

    exempt = (SOURCE_GATE_EXEMPT.get(pid) or {}).get("rules") or set()
    violations = []  # (rule, 位置, 说明)
    for f in _product_swift_sources(pdir):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            errs.append(f"源码闸门：源码读取失败 {f.relative_to(VAULT_ROOT)}（{e}）")
            continue
        rel = f.relative_to(VAULT_ROOT).as_posix()
        for i, line in enumerate(lines, 1):
            for label, pat in COLOR_LITERAL_RES:
                if pat.search(line):
                    violations.append(
                        ("color_literal", f"{rel}:{i}",
                         f"颜色字面量 {label}（须走 BrickUIKit Design.ColorPalette 令牌）"))
            if BARE_PRESENTATION_RE.search(line):
                violations.append(
                    ("bare_presentation", f"{rel}:{i}",
                     "裸弹层调用（须走 brick* 封装：.brickSheet / .brickAlert / .brickConfirm）"))

    exempted = False
    for rule, where, why in violations:
        if rule in exempt:
            exempted = True
            print(f"[warn] {pid} 源码闸门·豁免：{where} {why}")
        else:
            errs.append(f"源码闸门：{where} {why}")
    if exempted:
        note = (SOURCE_GATE_EXEMPT.get(pid) or {}).get("warn")
        if note:
            print(f"[warn] {pid} {note}")
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

    identity_key = IDENTITY_KEY_V2 if m.get("schema") == SCHEMA_V2 else IDENTITY_KEY_V1
    for f in sorted(set(MANIFEST_REQUIRED) | {identity_key}):
        if f not in m or m[f] in (None, ""):
            errs.append(f"manifest.json 缺少必填字段：{f}")

    if m.get("name") != mid:
        errs.append(f"name 与目录名不一致：manifest={m.get('name')!r}，目录={mid!r}")
    if m.get("kind") != "product":
        errs.append(f"kind 必须为 product，当前：{m.get('kind')!r}")
    errs.extend(verify_permission_risks(m))
    errs.extend(verify_source_gates(pdir, m))
    raw_id = m.get(identity_key, "")
    if not str(raw_id).startswith("com.shadeling.brick."):
        errs.append(f"{identity_key} 非法：{raw_id!r}（应以 com.shadeling.brick. 开头）")

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
        errs.extend(verify_version_consistency(pdir, m, zip_path))
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
