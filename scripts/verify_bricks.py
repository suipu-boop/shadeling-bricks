#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick Vault · 验证闸门（地基）。

发布前强制自检：扫描 bricks/*/brick.json，逐块做契约 + 完整性校验，
并核对 index.json 登记一致。**不过闸门不允许发布**（工厂 push 前必须过本闸门）。

校验项：
1. brick.json 5 字段契约（镜像内核 skill_library._normalize_brick_fields）
2. 元数据必填（name / summary / version / category / risk_level）
3. files 实现文件存在性（src 相对积木目录必须存在）
4. index.json 登记一致（name/version/category/risk_level/summary/path 对齐）
5. composition 引用完整性（requires / conflicts_with 引用的积木必须存在于库中）

权威实现：Shadeling 内核 runtime/skill_library.py（validate_skill_package）。
本脚本为镜像校验，契约变更需同步三处：内核 skill_library.py / 本脚本 / specs。

用法：
    python3 scripts/verify_bricks.py            # 校验全部
    python3 scripts/verify_bricks.py <name>     # 只校验指定积木
    python3 scripts/verify_bricks.py --strict   # 严格模式（元数据全字段必填）
"""
from __future__ import annotations

import argparse
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
# 元数据必填字段（宽松模式只查这些）
META_REQUIRED = {"name", "summary", "version", "category", "risk_level"}
# 严格模式补充字段（新积木应全有）
META_REQUIRED_STRICT = {"name", "summary", "version", "category", "risk_level",
                        "author", "description", "tags", "license", "source"}

# 与 index.json 对齐的字段
INDEX_ALIGN_FIELDS = ("name", "version", "category", "risk_level", "summary", "path")


class VerifyError(ValueError):
    """校验失败。"""


def _validate_5_fields(brick: dict, name: str) -> list:
    """5 字段契约校验，返回错误列表（空 = 通过）。"""
    errs = []

    risk = brick.get("risk_level", "low")
    if risk not in RISK_LEVELS:
        errs.append(f"risk_level 非法：{risk}（应为 {'/'.join(sorted(RISK_LEVELS))}）")

    caps = brick.get("capabilities") or []
    if not isinstance(caps, list) or not all(isinstance(c, str) and c.strip() for c in caps):
        errs.append("capabilities 必须是字符串数组")

    deps = brick.get("dependencies") or []
    if not isinstance(deps, list):
        errs.append("dependencies 必须是数组")
    else:
        for d in deps:
            if not isinstance(d, dict):
                errs.append("dependencies 每项必须是对象")
                continue
            dname = d.get("name")
            if not dname or not isinstance(dname, str) or not dname.strip():
                errs.append("dependencies 每项必须有 name")
            dtype = d.get("type", "skill")
            if dtype not in DEPENDENCY_TYPES:
                errs.append(f"dependencies.type 非法：{dtype}")

    res = brick.get("resources") or {}
    if not isinstance(res, dict):
        errs.append("resources 必须是对象")
    else:
        for k in ("memory_mb", "disk_mb"):
            if k in res and (not isinstance(res[k], int) or isinstance(res[k], bool) or res[k] < 0):
                errs.append(f"resources.{k} 必须是非负整数")
        ports = res.get("ports") or []
        if not isinstance(ports, list) or not all(
                isinstance(p, int) and not isinstance(p, bool) for p in ports):
            errs.append("resources.ports 必须是整数数组")
        if "network" in res and not isinstance(res["network"], bool):
            errs.append("resources.network 必须是布尔值")

    comp = brick.get("composition") or {}
    if not isinstance(comp, dict):
        errs.append("composition 必须是对象")
    else:
        for sub in ("requires", "conflicts_with"):
            if sub in comp and not isinstance(comp[sub], list):
                errs.append(f"composition.{sub} 必须是数组")
        scope = comp.get("memory_scope") or []
        if not isinstance(scope, list):
            errs.append("composition.memory_scope 必须是数组")
        else:
            for m in scope:
                if m not in MEMORY_SCOPES:
                    errs.append(f"composition.memory_scope 非法：{m}")
        if name and name in (comp.get("conflicts_with") or []):
            errs.append(f"composition.conflicts_with 不得包含自身 {name}")

    return errs


def _validate_meta(brick: dict, strict: bool) -> list:
    """元数据必填校验。"""
    errs = []
    required = META_REQUIRED_STRICT if strict else META_REQUIRED
    for k in required:
        v = brick.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            errs.append(f"元数据缺必填字段：{k}")
    name = brick.get("name") or ""
    if name and (not isinstance(name, str) or "/" in name or name.startswith(".")):
        errs.append(f"name 非法：{name!r}（需非空、不含 /、不以 . 开头）")
    return errs


def _validate_files(brick: dict, brick_dir: Path) -> list:
    """files 实现文件存在性：src 相对积木目录必须存在。"""
    errs = []
    files = brick.get("files") or []
    if not isinstance(files, list):
        errs.append("files 必须是数组")
        return errs
    for f in files:
        if not isinstance(f, dict):
            errs.append("files 每项必须是对象")
            continue
        src = f.get("src") or ""
        if not src:
            errs.append("files 每项必须有 src")
            continue
        if src.startswith("/") or ".." in src:
            errs.append(f"files.src 路径非法（不得绝对路径或含 ..）：{src}")
            continue
        if not (brick_dir / src).exists():
            errs.append(f"files.src 实现文件不存在：{src}")
    return errs


def _validate_index(brick: dict, name: str, index: dict) -> list:
    """index.json 登记一致：name/version/category/risk_level/summary/path 对齐。"""
    errs = []
    entries = index.get("bricks") or []
    entry = next((e for e in entries if e.get("name") == name), None)
    if entry is None:
        errs.append(f"index.json 未登记积木：{name}")
        return errs
    for field in INDEX_ALIGN_FIELDS:
        if field == "path":
            expected = f"bricks/{name}/"
        else:
            expected = brick.get(field)
        actual = entry.get(field)
        if actual != expected:
            errs.append(f"index.json {field} 不一致：brick.json={expected!r}，index={actual!r}")
    return errs


def _validate_composition_refs(brick: dict, name: str, all_names: set) -> list:
    """composition 引用完整性：requires / conflicts_with 引用的积木必须存在于库中。"""
    errs = []
    comp = brick.get("composition") or {}
    for sub in ("requires", "conflicts_with"):
        refs = comp.get(sub) or []
        for r in refs:
            if r not in all_names:
                errs.append(f"composition.{sub} 引用不存在的积木：{r}")
    return errs


def verify_brick(brick_dir: Path, index: dict, all_names: set, strict: bool) -> list:
    """校验单块积木，返回错误列表（空 = 通过）。"""
    errs = []
    json_path = brick_dir / "brick.json"
    if not json_path.exists():
        errs.append(f"缺 brick.json：{brick_dir.name}")
        return errs
    try:
        brick = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        errs.append(f"brick.json 解析失败：{e}")
        return errs

    name = brick.get("name") or brick_dir.name
    if name != brick_dir.name:
        errs.append(f"name 与目录名不一致：brick.json={name!r}，目录={brick_dir.name!r}")

    errs += _validate_meta(brick, strict)
    errs += _validate_5_fields(brick, name)
    errs += _validate_files(brick, brick_dir)
    errs += _validate_index(brick, name, index)
    errs += _validate_composition_refs(brick, name, all_names)
    return errs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Brick Vault 验证闸门")
    p.add_argument("name", nargs="?", help="只校验指定积木（默认全部）")
    p.add_argument("--strict", action="store_true", help="严格模式：元数据全字段必填")
    args = p.parse_args(argv)

    index = {}
    if INDEX_PATH.exists():
        try:
            index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[verify] index.json 解析失败：{e}")
            return 1

    all_names = {d.name for d in BRICKS_DIR.iterdir()
                 if d.is_dir() and not d.name.startswith(".")}

    targets = [BRICKS_DIR / args.name] if args.name else sorted(
        d for d in BRICKS_DIR.iterdir() if d.is_dir() and not d.name.startswith("."))

    total_errs = 0
    for t in targets:
        if not t.is_dir():
            print(f"[verify] 积木目录不存在：{t.name}")
            total_errs += 1
            continue
        errs = verify_brick(t, index, all_names, args.strict)
        if errs:
            total_errs += len(errs)
            print(f"[FAIL] {t.name}（{len(errs)} 项）")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"[OK] {t.name}")

    mode = "严格模式" if args.strict else "常规模式"
    if total_errs:
        print(f"\n[verify] 闸门未通过：{total_errs} 项错误（{mode}）。不过闸门不允许发布。")
        return 1
    print(f"\n[verify] 闸门通过：全部积木合规（{mode}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
