#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick Vault · 积木工厂脚手架（P3）。

一条命令造出「合规积木」：生成 bricks/<name>/brick.json（5 字段契约 + 基础元数据）、
README 骨架，并登记进 index.json。生成后自检通过才落盘。

用法：
    python3 scripts/new_brick.py <name> --summary "一句话" [选项]

示例：
    python3 scripts/new_brick.py translator \
        --summary "中英互译，走本地模型" \
        --category skill --risk low \
        --capabilities "text.translate,text.zh2en,text.en2zh"

契约权威定义在 Shadeling 内核仓库 runtime/skill_library.py（validate_skill_package）。
本脚本内置一份轻量镜像校验（只覆盖 5 字段核心规则），提交前仍须过内核 `make verify` 闸门。
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
BRICKS_DIR = VAULT_ROOT / "bricks"
INDEX_PATH = VAULT_ROOT / "index.json"

# —— 契约常量（与 Shadeling runtime/skill_library.py 保持一致，改动需同步）——
RISK_LEVELS = {"low", "medium", "high", "critical"}
DEPENDENCY_TYPES = {"skill", "binary", "python"}
MEMORY_SCOPES = {"session", "project", "user", "workspace", "longterm"}
CATEGORIES = {"skill", "connector", "tool", "doc"}

# —— 各 category 的默认资源/能力标签 ——
CATEGORY_DEFAULTS = {
    "skill": {"capabilities": [], "memory_mb": 64},
    "connector": {"capabilities": [], "memory_mb": 128},
    "tool": {"capabilities": [], "memory_mb": 32},
    "doc": {"capabilities": [], "memory_mb": 8},
}


class BrickError(ValueError):
    """生成的 brick 不合契约。"""


def _validate_5_fields(brick: dict, name: str) -> None:
    """轻量镜像校验：只覆盖 5 字段核心规则。权威校验在内核 validate_skill_package。"""
    risk = brick.get("risk_level", "low")
    if risk not in RISK_LEVELS:
        raise BrickError(f"risk_level 非法：{risk}")

    caps = brick.get("capabilities") or []
    if not isinstance(caps, list) or not all(isinstance(c, str) and c.strip() for c in caps):
        raise BrickError("capabilities 必须是字符串数组")

    deps = brick.get("dependencies") or []
    if not isinstance(deps, list):
        raise BrickError("dependencies 必须是数组")
    for d in deps:
        if not isinstance(d, dict) or not (d.get("name") or "").strip():
            raise BrickError("dependencies 每项必须是含 name 的对象")
        if d.get("type", "python") not in DEPENDENCY_TYPES:
            raise BrickError(f"dependencies.type 非法：{d.get('type')}")

    res = brick.get("resources") or {}
    if not isinstance(res, dict):
        raise BrickError("resources 必须是对象")
    for k in ("memory_mb", "disk_mb"):
        if k in res and (not isinstance(res[k], int) or isinstance(res[k], bool) or res[k] < 0):
            raise BrickError(f"resources.{k} 必须是非负整数")
    if "network" in res and not isinstance(res["network"], bool):
        raise BrickError("resources.network 必须是布尔值")

    comp = brick.get("composition") or {}
    if not isinstance(comp, dict):
        raise BrickError("composition 必须是对象")
    for sub in ("requires", "conflicts_with"):
        if sub in comp and not isinstance(comp[sub], list):
            raise BrickError(f"composition.{sub} 必须是数组")
    scope = comp.get("memory_scope") or []
    if not isinstance(scope, list):
        raise BrickError("composition.memory_scope 必须是数组")
    for m in scope:
        if m not in MEMORY_SCOPES:
            raise BrickError(f"composition.memory_scope 非法：{m}")
    if name and name in (comp.get("conflicts_with") or []):
        raise BrickError("composition.conflicts_with 不得包含自身")


def _skill_content_template(name: str, summary: str) -> str:
    """skill 类积木的默认 prompt 骨架，供后续填充。"""
    return (
        f"你是 Shadeling 的「{name}」助手。\n"
        f"职责：{summary}\n\n"
        "## 何时用\n"
        "（在此补充：用户说哪些话时触发本积木）\n\n"
        "## 怎么用\n"
        "（在此补充：具体操作步骤 / 可用工具）\n\n"
        "## 边界\n"
        "（在此补充：不做什么、权限前提、失败如何处理）\n"
    )


def build_brick(args) -> dict:
    name = args.name.strip()
    if not name or "/" in name or ".." in name or name.startswith("."):
        raise BrickError(f"积木名非法：{name!r}（需非空、不含 / 与 ..）")

    category = args.category
    risk = args.risk
    caps = [c.strip() for c in (args.capabilities or "").split(",") if c.strip()]
    deps = []
    for dep in (args.deps or "").split(","):
        dep = dep.strip()
        if dep:
            deps.append({"name": dep, "type": "python", "version": "*"})
    scope = [s.strip() for s in (args.memory_scope or "session").split(",") if s.strip()]
    trigger = [t.strip() for t in (args.trigger or "").split(",") if t.strip()]

    content = _skill_content_template(name, args.summary) if category == "skill" else ""

    brick = {
        "name": name,
        "summary": args.summary,
        "version": args.version,
        "author": args.author,
        "description": args.summary,
        "category": category,
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()] or [category, name],
        "license": args.license,
        "source": "builtin",
        "trigger": trigger,
        "content": content,
        "capabilities": caps,
        "dependencies": deps,
        "resources": {
            "memory_mb": args.memory_mb,
            "disk_mb": 5,
            "network": args.network,
            "ports": [],
        },
        "risk_level": risk,
        "composition": {
            "requires": [],
            "conflicts_with": [],
            "memory_scope": scope,
        },
    }
    _validate_5_fields(brick, name)
    return brick


def load_index() -> dict:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"schema": "brick-registry/v1", "bricks": []}
    return {"schema": "brick-registry/v1", "bricks": []}


def upsert_index(index: dict, brick: dict, name: str) -> dict:
    entry = {
        "name": name,
        "version": brick["version"],
        "category": brick["category"],
        "risk_level": brick["risk_level"],
        "summary": brick["summary"],
        "path": f"bricks/{name}/",
    }
    bricks = [b for b in index.get("bricks", []) if b.get("name") != name]
    bricks.append(entry)
    index["bricks"] = sorted(bricks, key=lambda b: b["name"])
    index["updated_at"] = datetime.date.today().isoformat()
    return index


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Brick Vault 积木工厂脚手架")
    p.add_argument("name", help="积木名（小写、不含空格，如 translator）")
    p.add_argument("--summary", required=True, help="一句话摘要")
    p.add_argument("--category", choices=sorted(CATEGORIES), default="skill")
    p.add_argument("--risk", choices=sorted(RISK_LEVELS), default="low")
    p.add_argument("--capabilities", help="能力标签，逗号分隔，如 text.translate,text.en2zh")
    p.add_argument("--deps", help="python 依赖，逗号分隔")
    p.add_argument("--network", action="store_true", help="声明需要联网")
    p.add_argument("--memory-scope", default="session", help="记忆域，逗号分隔（默认 session）")
    p.add_argument("--trigger", help="触发词，逗号分隔")
    p.add_argument("--tags", help="标签，逗号分隔（默认 category+name）")
    p.add_argument("--author", default="Shadeling")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--license", default="MIT")
    p.add_argument("--memory-mb", type=int, default=64, help="内存预算 MB（默认 64）")
    p.add_argument("--dry-run", action="store_true", help="只打印将生成的内容，不落盘")
    args = p.parse_args(argv)

    try:
        brick = build_brick(args)
    except BrickError as e:
        print(f"[new_brick] 校验失败：{e}")
        return 1

    out_dir = BRICKS_DIR / args.name
    out_json = out_dir / "brick.json"
    out_readme = out_dir / "README.md"

    if args.dry_run:
        print("[new_brick] dry-run（未落盘），将生成：")
        print(f"  {out_json.relative_to(VAULT_ROOT)}")
        print(f"  {out_readme.relative_to(VAULT_ROOT)}")
        print("  —— brick.json 预览 ——")
        print(json.dumps(brick, ensure_ascii=False, indent=2))
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(brick, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readme = [
        f"# {args.name}",
        "",
        f"> {args.summary}",
        "",
        "## 元信息",
        f"- 类别：{brick['category']}　风险：{brick['risk_level']}　版本：{brick['version']}",
        f"- 能力标签：{', '.join(brick['capabilities']) or '（待填）'}",
        f"- 依赖：{', '.join(d['name'] for d in brick['dependencies']) or '（无）'}",
        f"- 记忆域：{', '.join(brick['composition']['memory_scope'])}",
        "",
        "## 说明",
        "（在此补充积木的职责、用法、边界）",
        "",
    ]
    out_readme.write_text("\n".join(readme), encoding="utf-8")

    index = upsert_index(load_index(), brick, args.name)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[new_brick] 已生成合规积木：{out_json}")
    print(f"[new_brick] 已更新 index.json（共 {len(index['bricks'])} 个积木）")
    print("[new_brick] 提示：提交前请过内核 `make verify` 闸门")
    return 0


if __name__ == "__main__":
    sys.exit(main())
