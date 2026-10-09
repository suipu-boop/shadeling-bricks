#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 产品积木脚手架（Phase 4）——一条命令产出声明式产品工程骨架。

定位
----
与 ``new_brick.py``（v1 轻量积木：``bricks/<id>/brick.json``）互为姊妹：本脚本只产
``brick-app/v2`` **产品工程**（``products/<id>/``），不生成任何 Swift 工程。

产物结构::

    products/<id>/
      ├── manifest.json       # nav / ui / logic 三段齐备（契约 §3.6-1）
      ├── ui/main.json        # shadeling-ui/1 最小可渲染骨架（令牌全在 TokenMap 表内）
      ├── logic/<entry>       # jsonrpc-stdio/1 逻辑进程 stub（python3，0755）
      ├── README.md
      └── releases/           # 出包落位目录（pack_product.py 写入）

三条纪律（与仓库既有脚本同源，禁止绕过）
---------------------------------------
1. **包内 manifest 不写** ``sha256``：由 ``pack_product.py finalize`` 出包后回填
   （zip 无法包含自身哈希，pack 会硬拒）；``download_url`` 按发布路径预置。
2. **生成即自检**：ui 文档过 ``verify_ui_doc``（含令牌表硬校验），manifest 过字段级
   闸门（三段齐备 / theme 枚举 / brick_id 前缀 / logic.entry 落位 / permission_risks
   台账一致）——把「新工程天生不合规」挡在源头。
3. **发布闸门在出包之后**：``--pack`` 完成 pack + finalize（回填 sha256 与 index.json）
   后，再跑 ``scripts/verify_all.sh``。release zip / index 登记项在出包前必然缺失，
   属阶段差异、非缺陷。

用法::

    python3 scripts/new_product.py my-brick --title "我的积木" --icon tray
    python3 scripts/new_product.py my-brick --permissions fs.pick --pack
    python3 scripts/new_product.py my-brick --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
# 允许测试 / CI 指向临时 vault（不污染真实仓库）
VAULT_ROOT = Path(os.environ.get("BRICK_VAULT_ROOT") or SCRIPTS_DIR.parent)
PRODUCTS_DIR = VAULT_ROOT / "products"

sys.path.insert(0, str(SCRIPTS_DIR))

ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
BRICK_ID_PREFIX = "com.shadeling.brick."
SCHEMA_V2 = "brick-app/v2"
UI_ENGINE = "shadeling-ui/1"
THEMES = ("brick-light", "brick-dark")
RISK_LEVELS = ("low", "mid", "high", "app-level")
DEFAULT_QUOTA = {"ui_events_per_sec": 30, "max_nodes": 2000, "storage_mb": 128, "rss_mb": 512}
DEFAULT_ICON = "tray"

LOGIC_STUB = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""__ID__ · 逻辑进程 stub（jsonrpc-stdio/1）。

宿主通过 stdin/stdout 逐行 JSON-RPC 交互；``initialize`` 注入私有数据目录
（``private_dir``）与权限回执。本文件只做「进程可启动 + 请求可回声」的最小实现，
业务逻辑在此填充。

协议细则见 specs/Shadeling积木声明式UI架构设计与契约-v1.0.md §3.3；
完整参考实现见 products/wechat-mp/logic/wechat_mp。
"""

from __future__ import annotations

import json
import sys

BRICK_ID = "__BRICK_ID__"
VERSION = "__VERSION__"
PRIVATE_DIR = ""


def handle(method, params):
    """返回 (result, should_exit)。"""
    global PRIVATE_DIR
    if method == "initialize":
        PRIVATE_DIR = str(params.get("private_dir") or "")
        return {"ok": True, "brick_id": BRICK_ID, "version": VERSION}, False
    if method == "ping":
        return {"pong": True}, False
    if method == "shutdown":
        return {"ok": True}, True
    # 未实现的方法回显，便于联调期定位事件名
    return {"ok": True, "method": method, "echo": params}, False


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        method = msg.get("method") or ""
        result, stop = handle(method, msg.get("params") or {})
        sys.stdout.write(json.dumps(
            {"jsonrpc": "2.0", "id": msg.get("id"), "result": result},
            ensure_ascii=False) + "\\n")
        sys.stdout.flush()
        if stop:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


class ScaffoldError(ValueError):
    """脚手架入参或落盘不合契约。"""


# ---------------------------------------------------------------------------
# 模板构建
# ---------------------------------------------------------------------------

def build_ui_document(title: str, summary: str, version: str) -> dict:
    """最小可渲染骨架：header + summary + 横幅 + 空态卡 + 命令条。

    节点全部落在既有规则表内（组件 / props 键 / 图标白名单 / 令牌表），
    生成物即通过 ``verify_ui_doc``，不留「先例违规」。
    """
    return {
        "schema": UI_ENGINE,
        "version": 1,
        "state_snapshot": {
            "status_text": "就绪",
            "banner_visible": False,
            "banner_text": "",
            "busy": False,
            "item_count": 0,
            "items": [],
            "empty_hint": "还没有内容，点击「刷新」开始",
            "card_title": title,
            "card_subtitle": summary,
        },
        "root": {
            "type": "container",
            "id": "root",
            "props": {"direction": "vertical", "gap": "space.md", "padding": "space.lg",
                      "background": "surface.base"},
            "children": [
                {
                    "type": "container",
                    "id": "header",
                    "props": {"direction": "horizontal", "gap": "space.sm", "align": "center"},
                    "children": [
                        {"type": "icon", "id": "app_icon",
                         "props": {"name": DEFAULT_ICON, "size": "md", "color": "accent"}},
                        {"type": "text", "id": "app_title", "props": {"value": title, "style": "title"}},
                        {"type": "text", "id": "app_version",
                         "props": {"value": "v" + version, "style": "caption", "color": "text.secondary"}},
                    ],
                },
                {"type": "text", "id": "app_summary",
                 "props": {"value": summary, "style": "body", "color": "text.secondary", "lines": 2}},
                {"type": "overlay", "id": "status_banner",
                 "props": {"kind": "banner", "level": "info", "visible": "{{state.banner_visible}}",
                           "text": "{{state.banner_text}}"}},
                {"type": "card", "id": "main_card",
                 "props": {"title": "{{state.card_title}}", "subtitle": "{{state.card_subtitle}}",
                           "meta": "{{state.item_count}} 项", "tags": ["v" + version, "骨架"],
                           "actions": []}},
                {
                    "type": "container",
                    "id": "cmd_bar",
                    "props": {"direction": "horizontal", "gap": "space.sm", "align": "center"},
                    "children": [
                        {"type": "button", "id": "refresh_btn",
                         "props": {"label": "刷新", "style": "primary", "icon": "arrow.clockwise",
                                   "busy": "{{state.busy}}"},
                         "on": {"tap": "refresh"}},
                        {"type": "button", "id": "close_btn",
                         "props": {"label": "关闭", "style": "ghost", "icon": "xmark"},
                         "on": {"tap": "close"}},
                    ],
                },
                {"type": "text", "id": "status_line",
                 "props": {"value": "{{state.status_text}}", "style": "caption", "color": "text.secondary"}},
            ],
        },
    }


def build_manifest(args) -> dict:
    entry = args.id.replace("-", "_")
    manifest = {
        "schema": SCHEMA_V2,
        "brick_id": BRICK_ID_PREFIX + args.id,
        "name": args.id,
        "title": args.title,
        "version": args.version,
        "summary": args.summary,
        "author": args.author,
        "kind": "product",
        "nav": {"view_id": args.id, "title": args.title, "icon": args.icon, "order": args.order},
        "ui": {"engine": UI_ENGINE, "entry": "ui/main.json", "theme": args.theme},
        "logic": {"protocol": "jsonrpc-stdio/1", "entry": "logic/" + entry,
                  "runtime": "python3", "args": [], "env": {}},
        "permissions": list(args.permissions),
        "quota": dict(DEFAULT_QUOTA),
        # 预置发布路径：finalize 会逐字比对（不符即拒），故此处必须写标准 URL
        "download_url": (f"https://github.com/suipu-boop/shadeling-bricks/raw/main/"
                         f"products/{args.id}/releases/{args.version}/{args.id}-{args.version}.zip"),
        "release_notes": "初始骨架（new_product.py 生成）。",
    }
    if args.permissions:
        manifest["permission_risks"] = [
            {"permission": p, "level": args.permission_level, "status": "declared"}
            for p in args.permissions
        ]
    return manifest


def build_readme(manifest: dict) -> str:
    m = manifest
    return "\n".join([
        f"# {m['title']}（{m['name']}）",
        "",
        f"> {m['summary']}",
        "",
        "## 元信息",
        f"- 形态：`{m['schema']}`（声明式产品积木）　版本：{m['version']}",
        f"- 视图：`{m['nav']['view_id']}`（order={m['nav']['order']}）　主题：`{m['ui']['theme']}`",
        f"- 逻辑进程：`{m['logic']['entry']}`（{m['logic']['protocol']} / {m['logic']['runtime']}）",
        f"- 权限：{', '.join(m['permissions']) or '（无）'}",
        "",
        "## 结构",
        "| 路径 | 职责 |",
        "| --- | --- |",
        "| `manifest.json` | 身份 / nav / ui / logic / 权限 / 配额；发布元数据由 finalize 回填 |",
        "| `ui/main.json` | 声明式 UI 文档（shadeling-ui/1）：节点树 + 事件 + state 快照 |",
        f"| `{m['logic']['entry']}` | 逻辑进程（jsonrpc-stdio/1）：唯一数据面，填 state / 收事件 |",
        "",
        "## 纪律",
        "- 视觉只用 BrickUIKit 令牌：颜色 10 / 字号 5 / 间距 5 / 圆角 3，表外名装包即拒（4303）。",
        "- 弹层只用 `.brickSheet` / `.brickConfirm` / `BrickBanner` 对应声明（`overlay.kind`）。",
        f"- `manifest.logic.sha256` = {m['logic']['sha256'][:16]}…（判据③）；改了 stub 必须重算：",
        f"  `python3 scripts/new_product.py {m['name']} --rehash`。",
        "- 改 ui 文档后跑 `python3 scripts/verify_ui_doc.py products/" + m["name"] + "/ui/main.json`。",
        "",
        "## 出包",
        "```bash",
        f"python3 scripts/pack_product.py pack --product {m['name']} --version {m['version']}",
        f"python3 scripts/pack_product.py finalize --product {m['name']} --version {m['version']}",
        "bash scripts/verify_all.sh",
        "```",
        "",
        "## 说明",
        "（在此补充积木的职责、用法、边界）",
        "",
    ])


# ---------------------------------------------------------------------------
# 自检（生成即跑；发布闸门在出包后）
# ---------------------------------------------------------------------------

def selfcheck(pdir: Path, manifest: dict) -> list:
    errs: list = []
    try:
        import verify_ui_doc
    except ImportError:
        errs.append("无法导入 verify_ui_doc（scripts 目录不可用），自检降级跳过")
    else:
        ui_path = pdir / manifest["ui"]["entry"]
        try:
            document = json.loads(ui_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errs.append(f"{manifest['ui']['entry']} 解析失败：{e}")
        else:
            issues = verify_ui_doc.Issues()
            verify_ui_doc.verify_document(document, issues)
            errs.extend(f"{manifest['ui']['entry']}：{item}" for item in issues.items)

    try:
        import verify_products as vp
    except ImportError:
        errs.append("无法导入 verify_products（scripts 目录不可用），自检降级跳过")
    else:
        errs.extend(vp.verify_required_sections(manifest))
        for fn in ("verify_ui_theme", "verify_logic_env", "verify_permission_risks"):
            check = getattr(vp, fn, None)
            if callable(check):
                errs.extend(check(manifest))
        for fn in ("verify_logic_entry_local", "verify_logic_hash_local"):
            check = getattr(vp, fn, None)
            if callable(check):
                errs.extend(check(pdir, manifest))
    
    return errs


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="v2 产品积木脚手架（brick-app/v2）")
    p.add_argument("id", help="产品 id（小写字母/数字/短横线，2~32 位，如 my-brick）")
    p.add_argument("--title", help="中文标题（默认取 id）")
    p.add_argument("--summary", default="（在此填写一句话职责）", help="一句话职责")
    p.add_argument("--version", default="1.0.0", help="初始版本（默认 1.0.0）")
    p.add_argument("--icon", default=DEFAULT_ICON, help=f"SF Symbol 图标（默认 {DEFAULT_ICON}）")
    p.add_argument("--order", type=int, default=200, help="导航排序（默认 200）")
    p.add_argument("--author", default="Shadeling", help="作者（默认 Shadeling）")
    p.add_argument("--theme", default="brick-light", choices=list(THEMES),
                   help="ui.theme（默认 brick-light，契约 §3.3）")
    p.add_argument("--permissions", nargs="*", default=[],
                   help="权限清单（同时登记 permission_risks，status=declared）")
    p.add_argument("--permission-level", default="mid", choices=list(RISK_LEVELS),
                   help="permission_risks 级别（默认 mid）")
    p.add_argument("--pack", action="store_true",
                   help="生成后直接 pack + finalize（出包并登记 index.json）")
    p.add_argument("--rehash", action="store_true",
                   help="重算 logic.entry 的 sha256 并回填 manifest（改过 stub 后必做）")
    p.add_argument("--dry-run", action="store_true", help="只预览，不落盘")
    p.add_argument("--force", action="store_true", help="目标目录已存在时覆盖骨架文件")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    args.title = args.title or args.id

    if not ID_PATTERN.match(args.id):
        print(f"[new_product] id 非法：{args.id!r}（须为小写字母开头的 2~32 位字母/数字/短横线）")
        return 1
    icon_ok = True
    try:
        import verify_ui_doc
        icon_ok = args.icon in verify_ui_doc.ICON_WHITELIST
    except ImportError:
        pass
    if not icon_ok:
        print(f"[new_product] 图标不在白名单：{args.icon}（契约 §4.10，需先与 Swift BrickIconWhitelist 同步）")
        return 1

    manifest = build_manifest(args)
    ui_doc = build_ui_document(args.title, args.summary, args.version)
    logic_text = (LOGIC_STUB
                  .replace("__ID__", args.id)
                  .replace("__BRICK_ID__", manifest["brick_id"])
                  .replace("__VERSION__", args.version))
    # logic.sha256 是发布闸门判据③的必登记项（§3.6-7）：生成即按最终字节算好，
    # 否则包在 _check_zip 阶段必被拒；改过 stub 用 --rehash 重算。
    manifest["logic"]["sha256"] = hashlib.sha256(logic_text.encode("utf-8")).hexdigest()
    readme = build_readme(manifest)

    pdir = PRODUCTS_DIR / args.id

    if args.rehash:
        mpath = pdir / "manifest.json"
        if not mpath.exists():
            print(f"[new_product] 产物不存在，无法重算：{pdir.relative_to(VAULT_ROOT)}")
            return 1
        current = json.loads(mpath.read_text(encoding="utf-8"))
        entry = pdir / str((current.get("logic") or {}).get("entry") or "")
        if not entry.is_file():
            print(f"[new_product] logic.entry 不存在：{(current.get('logic') or {}).get('entry')}")
            return 1
        digest = hashlib.sha256(entry.read_bytes()).hexdigest()
        current.setdefault("logic", {})["sha256"] = digest
        mpath.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[new_product] 已重算 logic.sha256：{digest}")
        errs = selfcheck(pdir, current)
        if errs:
            print(f"[new_product] 自检未通过（{len(errs)} 项）：")
            for e in errs:
                print(f"    - {e}")
            return 1
        print("[new_product] 自检通过；注意 zip 内逻辑与 manifest 哈希需同步——"
              "发布前须重新 pack + finalize")
        return 0
    targets = {
        pdir / "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        pdir / manifest["ui"]["entry"]: json.dumps(ui_doc, ensure_ascii=False, indent=2) + "\n",
        pdir / manifest["logic"]["entry"]: logic_text,
        pdir / "README.md": readme,
    }

    if args.dry_run:
        print("[new_product] dry-run（未落盘），将生成：")
        for path in targets:
            print(f"  {path.relative_to(VAULT_ROOT)}")
        print("  —— manifest.json 预览 ——")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if pdir.exists() and not args.force:
        print(f"[new_product] 目标已存在：{pdir.relative_to(VAULT_ROOT)}"
              f"（需覆盖骨架请加 --force；已存在的文件不会被静默改写）")
        return 1

    for path, text in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    os.chmod(pdir / manifest["logic"]["entry"], 0o755)
    (pdir / "releases").mkdir(exist_ok=True)
    (pdir / "releases" / ".gitkeep").touch()

    print(f"[new_product] 已生成产品工程：{pdir.relative_to(VAULT_ROOT)}")
    for path in targets:
        print(f"        {path.relative_to(VAULT_ROOT)}")

    errs = selfcheck(pdir, manifest)
    if errs:
        print(f"[new_product] 自检未通过（{len(errs)} 项）：")
        for e in errs:
            print(f"    - {e}")
        return 1
    print("[new_product] 自检通过：ui 文档（含令牌表）+ manifest 字段级闸门")

    if args.pack:
        try:
            import pack_product
            pack_product.pack(args.id, args.version)
            pack_product.finalize(args.id, args.version)
        except Exception as e:  # noqa: BLE001
            print(f"[new_product] 出包失败：{e}")
            return 1
        print("[new_product] 已出包并登记 index.json；发布前请跑：bash scripts/verify_all.sh")
    else:
        print("[new_product] 下一步（出包 + 登记）：")
        print(f"        python3 scripts/pack_product.py pack --product {args.id} --version {args.version}")
        print(f"        python3 scripts/pack_product.py finalize --product {args.id} --version {args.version}")
        print("        bash scripts/verify_all.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
