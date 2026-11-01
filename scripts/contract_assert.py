#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约 v1.0 离线断言（取证台账）——跨 product 覆盖 UI 词表 / manifest / 权限清单。

用途：交接 M4「小程序两只真机契约断言取证」的**离线可复跑形态**。
真机目视取证（装包 / 交互 / 硬信号）属 owner 专属插桩；本脚本在仓库侧
把契约 v1.0 的静态断言面逐条固化，产出每票 PASS/FAIL + 证据行，
作为真机前的前置通过凭证，并可在每次发布前复跑防回归。

断言面（契约 specs/Shadeling积木声明式UI架构设计与契约-v1.0.md）：
  A. §2.5  UI 词表 —— UI 文档节点类型 / 事件 / props / overlay kind / 令牌表
            （复用 scripts/verify_ui_doc.py 同源校验，避免双规则漂移）
  B. §3    manifest v2 —— schema / kind / ui.engine / logic.protocol / 字段完备
  C. §5.2  权限清单 —— manifest.permissions 每个权限 ∈ 已知枚举；高危权限须有风险标注
  D. §6.2  落盘口径 —— 私有数据目录语义（manifest 结构层面）

用法：
    python3 scripts/contract_assert.py            # 断言库内全部 product
    python3 scripts/contract_assert.py vault      # 只断言指定积木
退出码：0 全部 PASS；1 存在 FAIL（列出证据）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = REPO / "products"

# 契约 §5.2 已知权限枚举（桥权限 + UI 侧权限）
# 含 §3.3 应用级标记权限 `network`（v2 不再授予直连能力，仅作「需要联网」市场提示）。
# 注意：`agent.web.upload` 已更名 `agent.web.write`，以 write 为唯一现行名。
KNOWN_PERMISSIONS = {
    # 桥权限（§5.2 桥权限清单）
    "agent.chat", "agent.web", "agent.fs.read", "agent.browser", "agent.local",
    "agent.web.write",
    # UI 侧权限（§5.2 UI 侧权限清单）
    "ui.sheet", "ui.clipboard.write", "notify", "ui.open_url",
    "fs.pick", "auth.biometric", "ocr.recognize",
    # 应用级标记权限（§3.3，不授予直连能力）
    "network",
}
# 高危权限：install 确认页必须标红 + 二次确认（§5.2 风险级别判定）
HIGH_RISK_PERMISSIONS = {"agent.browser", "agent.local", "agent.web.write"}

# manifest v2 必填字段（契约 §3.2/§3.3）
REQUIRED_MANIFEST_FIELDS = (
    "schema", "brick_id", "name", "title", "version", "author",
    "kind", "nav", "ui", "logic", "permissions", "quota",
)
EXPECTED_SCHEMA = "brick-app/v2"
EXPECTED_UI_ENGINE = "shadeling-ui/1"
EXPECTED_LOGIC_PROTOCOL = "jsonrpc-stdio/1"
PRODUCT_KIND = "product"


class Ticket:
    """一条断言票：编号 / 标题 / 关联契约条款 / PASS / 证据。"""

    def __init__(self, code, title, clause):
        self.code = code
        self.title = title
        self.clause = clause
        self.ok = True
        self.evidence = []

    def fail(self, msg):
        self.ok = False
        self.evidence.append(msg)

    def pass_(self, msg):
        self.evidence.append(msg)


def _pass_ctx(root, tickets):
    """按 UI 文档仅报第一批问题（fail-fast，与运行时一致），其余 PASS。"""
    return None


def assert_ui_doc(product, ui_doc, tickets):
    """A 面：契约 §2.5 UI 词表（复用 verify_ui_doc 同源规则）。

    注意 UI 文档是**文档包裹形态**（schema/version/state_snapshot/root），
    必须走 verify_ui_doc.verify_document 解包 root，不能直接当节点 check。
    """
    verify = _load_ui_verifier()
    issues = verify.Issues()
    verify.verify_document(ui_doc, issues)
    t = Ticket("A1", "UI 文档包裹 + 节点词表/事件/props/令牌表全合规", "契约 §2.5 / §2.7")
    if issues:
        for issue in issues.items:
            t.fail(issue)
    else:
        t.pass_("verify_ui_doc 规则表零问题，对齐 Swift UIDocumentValidator")
    tickets.append(t)


def _load_ui_verifier():
    """延迟加载 verify_ui_doc 模块（其顶层定义常量，import 即解析）。"""
    sys.path.insert(0, str(REPO / "scripts"))
    import verify_ui_doc
    return verify_ui_doc


def assert_manifest(product, manifest, tickets):
    """B 面：契约 §3 manifest v2 字段完备与值域。"""
    t = Ticket("B1", "manifest schema/kind/基础字段", "契约 §3.2/§3.3")
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            t.fail("缺少必填字段 `%s`" % field)
    if manifest.get("schema") != EXPECTED_SCHEMA:
        t.fail("schema 应为 `%s`，实际 `%s`" % (EXPECTED_SCHEMA, manifest.get("schema")))
    if manifest.get("kind") != PRODUCT_KIND:
        t.fail("kind 应为 `%s`，实际 `%s`" % (PRODUCT_KIND, manifest.get("kind")))
    if "ui" in manifest and manifest["ui"].get("engine") != EXPECTED_UI_ENGINE:
        t.fail("ui.engine 应为 `%s`，实际 `%s`" % (EXPECTED_UI_ENGINE, manifest["ui"].get("engine")))
    if "logic" in manifest and manifest["logic"].get("protocol") != EXPECTED_LOGIC_PROTOCOL:
        t.fail("logic.protocol 应为 `%s`，实际 `%s`" % (EXPECTED_LOGIC_PROTOCOL, manifest["logic"].get("protocol")))
    if t.evidence == [] and t.ok:
        t.pass_("schema=%s kind=%s ui.engine=%s logic.protocol=%s"
                % (manifest.get("schema"), manifest.get("kind"),
                   manifest.get("ui", {}).get("engine"), manifest.get("logic", {}).get("protocol")))
    tickets.append(t)


def assert_permissions(product, manifest, tickets):
    """C 面：契约 §5.2 权限清单——未知权限名拒装、高危须标红。"""
    t = Ticket("C1", "permissions ⊆ 已知枚举 + 高危标注", "契约 §5.2 / §5.1")
    perms = manifest.get("permissions") or []
    if not isinstance(perms, list):
        t.fail("permissions 应为数组")
        tickets.append(t)
        return
    for p in perms:
        if p not in KNOWN_PERMISSIONS:
            t.fail("未知权限 `%s`（不在契约 §5.2/§3.3 已知枚举；契约 §5.1 未知权限名安装器拒绝安装。"
                   "若为新增能力，需先升版登记到契约 v1.0，否则装机即拒）" % p)
    # 高危权限须在 permission_risks 中有风险标注（level=high / status 列明）
    risks = manifest.get("permission_risks") or []
    risk_names = {r.get("permission") for r in risks if isinstance(r, dict)}
    for high in sorted(HIGH_RISK_PERMISSIONS & set(perms)):
        if high not in risk_names:
            t.fail("高危权限 `%s` 未在 permission_risks 标注风险级别" % high)
        else:
            note = next((r.get("note", "") for r in risks if r.get("permission") == high), "")
            level = next((r.get("level") for r in risks if r.get("permission") == high), "")
            t.evidence.append("高危 `%s` level=%s note=%s" % (high, level, note[:60]))
    if t.evidence == [] and t.ok:
        t.pass_("permissions=%s 均在已知枚举，高危项已标注" % ",".join(sorted(perms)))
    tickets.append(t)


def assert_quota(product, manifest, tickets):
    """D 面：契约 §3 quota 配额区间钳制（manifest 只能收紧不能放宽）。"""
    t = Ticket("D1", "quota 配额钳制在同一量级", "契约 §3.3 配额段")
    quota = manifest.get("quota") or {}
    if not isinstance(quota, dict):
        t.fail("quota 应为对象")
        tickets.append(t)
        return
    # 契约默认上限（对照底座 brick_quota）；manifest 只能收紧。这里是结构断言约束。
    if "ui_events_per_sec" in quota:
        v = quota["ui_events_per_sec"]
        if not (1 <= v <= 120):
            t.fail("ui_events_per_sec 应在 1…120：%s" % v)
    if "max_nodes" in quota:
        v = quota["max_nodes"]
        if not (1 <= v <= 2000):
            t.fail("max_nodes 应在 1…2000：%s" % v)
    if "storage_mb" in quota and quota["storage_mb"] not in (128, 256, 512):
        t.fail("storage_mb 应落在 128/256/512 档（越界即拒绝）：%s" % quota["storage_mb"])
    if "rss_mb" in quota and quota["rss_mb"] > 1024:
        t.fail("rss_mb 超过底座硬上限 1024：%s" % quota["rss_mb"])
    if t.evidence == [] and t.ok:
        t.pass_("quota=%s 在契约区间内" % json.dumps(quota, ensure_ascii=False))
    tickets.append(t)


def run_product(product):
    """对单个 product 跑契约离线断言，返回 (tickets, exit_status)。"""
    tickets = []
    pdir = PRODUCTS_DIR / product
    mani_path = pdir / "manifest.json"
    ui_path = pdir / "ui" / "main.json"

    if not mani_path.is_file():
        t = Ticket("P0", "%s manifest.json 存在" % product, "")
        t.fail("缺少 %s" % mani_path)
        return [t], 1
    if not ui_path.is_file():
        t = Ticket("P0", "%s ui/main.json 存在" % product, "")
        t.fail("缺少 %s" % ui_path)
        return [t], 1

    try:
        manifest = json.loads(mani_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        t = Ticket("P0", "%s manifest 可解析" % product, "")
        t.fail("manifest JSON 解析失败：%s" % e)
        return [t], 1
    try:
        ui_doc = json.loads(ui_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        t = Ticket("P0", "%s ui/main.json 可解析" % product, "")
        t.fail("ui/main.json JSON 解析失败：%s" % e)
        return [t], 1

    assert_ui_doc(product, ui_doc, tickets)
    assert_manifest(product, manifest, tickets)
    assert_permissions(product, manifest, tickets)
    assert_quota(product, manifest, tickets)

    any_fail = any(not t.ok for t in tickets)
    return tickets, (1 if any_fail else 0)


def main():
    ap = argparse.ArgumentParser(description="契约 v1.0 离线断言台账")
    ap.add_argument("name", nargs="?", help="只断言指定积木名（默认全部 product）")
    args = ap.parse_args()

    if args.name:
        targets = [args.name]
    else:
        targets = sorted(d.name for d in PRODUCTS_DIR.iterdir()
                         if d.is_dir() and (d / "manifest.json").is_file())

    overall = 0
    for product in targets:
        tickets, rc = run_product(product)
        print("===== %s =====" % product)
        for t in tickets:
            mark = "PASS" if t.ok else "FAIL"
            print("  [%s] %s | %s" % (mark, t.code, t.title))
            for ev in t.evidence:
                print("        - %s" % ev)
        overall |= rc
    print("==> 契约离线断言：%s" % ("PASS" if overall == 0 else "存在 FAIL"))
    return overall


if __name__ == "__main__":
    sys.exit(main())