#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品积木发布闸门自动化测试（市场 V2）。

隔离策略：全部用例在临时目录（tempfile.mkdtemp）内构造产品库，
不触碰真实 products/ 与 index.json。
"""
import hashlib
import plistlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLIST_VERSION_KEY = "CFBundleShortVersionString"  # 与 verify_products 同源
sys.path.insert(0, str(ROOT / "scripts"))

from verify_products import (  # noqa: E402
    verify_logic_env,
    verify_product,
    verify_required_sections,
    verify_ui_document,
    verify_v2_declarative_gates,
)


def make_manifest(name="demo", version="1.0.0", kind="product", **overrides):
    m = {
        "schema": "brick-app/v1",
        "id": f"com.shadeling.brick.{name}",
        "name": name,
        "title": "Demo",
        "version": version,
        "author": "Shadeling",
        "summary": "test product",
        "kind": kind,
        "bundle": "Demo.app",
        "permissions": [],
        "download_url": f"https://example.com/{name}-{version}.zip",
        "sha256": "0" * 64,
    }
    m.update(overrides)
    return m


def zip_manifest(manifest):
    """包内 manifest：只带身份字段（剥掉仓库侧发布元数据），与出包脚本 stage 一致。"""
    return {k: v for k, v in manifest.items() if k not in ("sha256", "download_url")}


def write_product_zip(zip_path, manifest, with_manifest=True, with_bundle=True):
    with zipfile.ZipFile(zip_path, "w") as zf:
        if with_bundle:
            # E1.1 版本一致性闸门：包内 Info.plist 须携带与 manifest.version 一致的
            # CFBundleShortVersionString（历史坑见 verify_version_consistency 注释）
            zf.writestr("Demo.app/Contents/Info.plist",
                        plistlib.dumps({PLIST_VERSION_KEY: manifest.get("version", "")}).decode("utf-8"))
        if with_manifest:
            zf.writestr("manifest.json", json.dumps(zip_manifest(manifest), ensure_ascii=False))


def make_product(vault: Path, name="demo", version="1.0.0", manifest=None,
                 with_manifest=True, with_bundle=True):
    """构造 products/<name>/ 目录：manifest + releases zip（含包内 manifest）+ index 登记。"""
    pdir = vault / "products" / name
    rel = pdir / "releases" / version
    rel.mkdir(parents=True, exist_ok=True)
    zip_path = rel / f"{name}-{version}.zip"
    if manifest is None:
        manifest = make_manifest(name=name, version=version)
    write_product_zip(zip_path, manifest, with_manifest=with_manifest, with_bundle=with_bundle)
    manifest["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (pdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    index = {"products": [{k: manifest.get(k) for k in
                           ("name", "version", "kind", "download_url", "sha256")}]}
    return pdir, index


# ——————————————————————————————————————————————————————————————
# C4 声明式（v2）闸门用例（2026-10-04 新增；2026-10-06 按 owner 拍板 C/A/B/B 扩至五项）
#   ① 三段硬卡点 nav/ui/logic（A）  ② ui.entry 存在且可解析  ③ 无裸弹层调用
#   ④ logic.entry 已签名或哈希登记（C）  ⑤ logic.env 键白名单（B）
# ——————————————————————————————————————————————————————————————

def ui_doc(root=None):
    """最小合法 UI 文档（§2.2）：单行文本。"""
    if root is None:
        root = {"type": "container", "id": "root",
                "props": {"direction": "vertical", "gap": 16},
                "children": [{"type": "text", "id": "title", "props": {"value": "hi"}}]}
    return {"schema": "shadeling-ui/1", "version": 1, "root": root}


def deep_root(levels):
    """构造 levels+1 层嵌套的 container 链（root 深度 = levels+1）。"""
    node = {"type": "text", "id": "leaf", "props": {"value": "x"}}
    for i in range(levels):
        node = {"type": "container", "id": f"c{i}", "children": [node]}
    return node


def make_v2_manifest(name="demo", version="1.0.0", ui_entry="ui/main.json",
                     logic_entry="logic/main.py", logic_sha256=None,
                     logic_signature=None, **overrides):
    logic = {"entry": logic_entry} if logic_entry else {}
    if logic_sha256 is not None:
        logic["sha256"] = logic_sha256
    if logic_signature is not None:
        logic["signature"] = logic_signature
    m = {
        "schema": "brick-app/v2",
        "brick_id": f"com.shadeling.brick.{name}",
        "name": name,
        "title": "Demo V2",
        "version": version,
        "author": "Shadeling",
        "summary": "test v2 product",
        "kind": "product",
        "nav": {"view_id": name, "title": "Demo V2", "icon": "square.grid.2x2", "order": 1},
        "ui": {"entry": ui_entry} if ui_entry else {},
        "logic": logic,
        "permissions": [],
        "download_url": f"https://example.com/{name}-{version}.zip",
        "sha256": "0" * 64,
    }
    m.update(overrides)
    return m


def make_v2_product(vault: Path, name="demo", version="1.0.0", manifest=None,
                    ui=None, logic_bytes=b"print('hi')", ui_text=None,
                    ui_in_zip=True, logic_in_zip=True, inner_manifest=True):
    """构造 v2 产品目录：ui/logic 入口 + 包内 manifest + index 登记。"""
    pdir = vault / "products" / name
    rel = pdir / "releases" / version
    rel.mkdir(parents=True, exist_ok=True)
    zip_path = rel / f"{name}-{version}.zip"
    if manifest is None:
        manifest = make_v2_manifest(
            name=name, version=version,
            logic_sha256=hashlib.sha256(logic_bytes).hexdigest())
    ui = ui_doc() if ui is None else ui
    m_ui = manifest.get("ui") if isinstance(manifest.get("ui"), dict) else {}
    m_logic = manifest.get("logic") if isinstance(manifest.get("logic"), dict) else {}
    with zipfile.ZipFile(zip_path, "w") as zf:
        if ui_in_zip and m_ui.get("entry"):
            zf.writestr(m_ui["entry"],
                        ui_text if ui_text is not None else json.dumps(ui, ensure_ascii=False))
        if logic_in_zip and m_logic.get("entry"):
            zf.writestr(m_logic["entry"], logic_bytes)
        if inner_manifest:
            zf.writestr("manifest.json",
                        json.dumps(zip_manifest(manifest), ensure_ascii=False))
    # 仓库侧 logic.entry 落位（verify_logic_entry_local / verify_logic_hash_local 口径）
    if m_logic.get("entry") and logic_bytes is not None:
        repo_logic = pdir / str(m_logic["entry"])
        repo_logic.parent.mkdir(parents=True, exist_ok=True)
        repo_logic.write_bytes(logic_bytes)
    manifest["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (pdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                        encoding="utf-8")
    index = {"products": [{k: manifest.get(k) for k in
                           ("name", "version", "kind", "download_url", "sha256")}]}
    return pdir, index


def patch_inner_manifest(pdir: Path, index: dict, mutate):
    """重写 zip 内 manifest 并同步 sha256，隔离「包内 manifest 不一致」用例。"""
    zip_path = next((pdir / "releases").glob("*/*.zip"))
    m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(zip_path) as zf:
        others = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
    inner = zip_manifest(m)
    mutate(inner)
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(inner, ensure_ascii=False))
        for n, b in others.items():
            zf.writestr(n, b)
    m["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (pdir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    index["products"][0]["sha256"] = m["sha256"]


class VerifyProductsTest(unittest.TestCase):

    def test_ok_product_passes(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            self.assertEqual(verify_product(pdir, index), [])

    def test_missing_manifest_field(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            del m["download_url"]
            (pdir / "manifest.json").write_text(
                json.dumps(m, ensure_ascii=False), encoding="utf-8")
            errs = verify_product(pdir, index)
            self.assertTrue(any("download_url" in e for e in errs))

    def test_kind_must_be_product(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td), manifest=make_manifest(kind="system"))
            errs = verify_product(pdir, index)
            self.assertTrue(any("kind 必须为 product" in e for e in errs))

    def test_name_mismatch_dir(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            m["name"] = "other"
            (pdir / "manifest.json").write_text(
                json.dumps(m, ensure_ascii=False), encoding="utf-8")
            errs = verify_product(pdir, index)
            self.assertTrue(any("name 与目录名不一致" in e for e in errs))

    def test_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            m["sha256"] = "1" * 64
            (pdir / "manifest.json").write_text(
                json.dumps(m, ensure_ascii=False), encoding="utf-8")
            errs = verify_product(pdir, index)
            self.assertTrue(any("sha256 不一致" in e for e in errs))

    def test_not_registered_in_index(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, _ = make_product(Path(td))
            errs = verify_product(pdir, {"products": []})
            self.assertTrue(any("未登记" in e for e in errs))

    # —— zip 内容闸门（2026-09-25 新增：wechat-mp / vault 曾因包内缺 manifest 装不上）——

    def test_zip_without_manifest_fails(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td), with_manifest=False)
            errs = verify_product(pdir, index)
            self.assertTrue(any("zip 内缺 manifest.json" in e for e in errs))

    def test_zip_without_bundle_fails(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td), with_bundle=False)
            errs = verify_product(pdir, index)
            self.assertTrue(any("zip 内缺入口 bundle" in e for e in errs))

    def test_zip_manifest_identity_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            zip_path = pdir / "releases" / "1.0.0" / "demo-1.0.0.zip"
            stale = make_manifest(version="9.9.9")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("Demo.app/Contents/Info.plist", "<plist/>")
                zf.writestr("manifest.json", json.dumps(zip_manifest(stale), ensure_ascii=False))
            # 重写 zip 后同步 sha256，隔离出「包内 manifest 不一致」这一条
            digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            m["sha256"] = digest
            (pdir / "manifest.json").write_text(
                json.dumps(m, ensure_ascii=False), encoding="utf-8")
            index["products"][0]["sha256"] = digest
            errs = verify_product(pdir, index)
            self.assertTrue(any("zip 内 manifest 与仓库 manifest 不一致" in e for e in errs))

    def test_zip_manifest_must_not_carry_sha256(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_product(Path(td))
            zip_path = pdir / "releases" / "1.0.0" / "demo-1.0.0.zip"
            inner = zip_manifest(make_manifest())
            inner["sha256"] = "0" * 64
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("Demo.app/Contents/Info.plist", "<plist/>")
                zf.writestr("manifest.json", json.dumps(inner, ensure_ascii=False))
            digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            m["sha256"] = digest
            (pdir / "manifest.json").write_text(
                json.dumps(m, ensure_ascii=False), encoding="utf-8")
            index["products"][0]["sha256"] = digest
            errs = verify_product(pdir, index)
            self.assertTrue(any("不应携带 sha256" in e for e in errs))

    def test_real_products_pass_gate(self):
        """仓库真实产品积木必须过闸门（防止 zip 内漏 manifest 的包再被提交）。"""
        products_dir = ROOT / "products"
        if not products_dir.exists():
            self.skipTest("products/ 不存在")
        index_path = ROOT / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        dirs = sorted(d for d in products_dir.iterdir()
                      if d.is_dir() and not d.name.startswith("."))
        if not dirs:
            self.skipTest("products/ 为空")
        for d in dirs:
            with self.subTest(product=d.name):
                self.assertEqual(verify_product(d, index), [])

    # —— C4 声明式（v2）三项闸门 ——

    def test_v2_valid_product_passes(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_v2_product(Path(td))
            self.assertEqual(verify_product(pdir, index), [])

    def test_v2_compat_v1_product_skips_gates(self):
        """§3.5 兼容期：v1 bundle 形态无 ui/logic 段，三项闸门不适用。"""
        with tempfile.TemporaryDirectory() as td:
            pdir, _ = make_product(Path(td))
            zip_path = next((pdir / "releases").glob("*/*.zip"))
            m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(verify_v2_declarative_gates(zip_path, m), [])

    # ① 三段硬卡点 nav / ui / logic（§3.6-1，2026-10-06 owner 拍板 A）

    def test_v2_missing_nav_section(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_sha256="0" * 64)
            del m["nav"]
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("缺 nav 段（整段缺失）" in e for e in verify_product(pdir, index)))

    def test_v2_section_present_but_not_object(self):
        for key in ("nav", "ui", "logic"):
            with self.subTest(section=key):
                m = make_v2_manifest(logic_sha256="0" * 64)
                m[key] = "nope"
                errs = verify_required_sections(m)
                self.assertTrue(any(f"缺 {key} 段（存在但不是对象）" in e for e in errs), errs)

    def test_v2_missing_section_reported_before_entry_errors(self):
        """缺段早检须先于字段级文案报出（与宿主安装流程同序，避免被「缺 nav.view_id」淹没）。"""
        m = make_v2_manifest(ui_entry=None, logic_entry=None)
        del m["nav"]
        errs = verify_v2_declarative_gates(Path("/nonexistent.zip"), m)
        self.assertEqual(len(errs), 1)
        self.assertIn("缺 nav 段（整段缺失）", errs[0])

    def test_v1_not_gated_by_required_sections(self):
        """§3.5 兼容期：v1（含未标 schema 的历史包）不强制三段。"""
        self.assertEqual(verify_required_sections(make_manifest()), [])
        unmarked = make_manifest()
        unmarked.pop("schema")
        self.assertEqual(verify_required_sections(unmarked), [])

    # ⑤ logic.env 键白名单（§3.3 / §3.6-5，2026-10-06 owner 拍板 B）

    def test_v2_logic_env_empty_passes(self):
        self.assertEqual(verify_logic_env(make_v2_manifest(logic_sha256="0" * 64)), [])

    def test_v2_logic_env_absent_passes(self):
        m = make_v2_manifest(logic_sha256="0" * 64)
        self.assertEqual(verify_logic_env(m), [])

    def test_v2_logic_env_unknown_key_rejected(self):
        m = make_v2_manifest(logic_sha256="0" * 64)
        m["logic"]["env"] = {"PATH": "/usr/bin", "SHADELING_TMP": "/tmp"}
        errs = verify_logic_env(m)
        self.assertTrue(any("未登记键" in e and "PATH" in e for e in errs), errs)

    def test_v2_logic_env_unknown_key_fails_in_product(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_sha256="0" * 64)
            m["logic"]["env"] = {"HOME": "/Users/x"}
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("未登记键" in e for e in verify_product(pdir, index)))

    def test_v2_logic_env_non_object_rejected(self):
        m = make_v2_manifest(logic_sha256="0" * 64)
        m["logic"]["env"] = []
        self.assertTrue(any("必须是对象" in e for e in verify_logic_env(m)))

    # ② ui.entry 存在且可解析

    def test_v2_missing_ui_section(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_sha256="0" * 64)
            del m["ui"]
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("缺 ui 段" in e for e in verify_product(pdir, index)))

    def test_v2_missing_ui_entry(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(ui_entry=None, logic_sha256="0" * 64)
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("缺 ui.entry" in e for e in verify_product(pdir, index)))

    def test_v2_ui_entry_absent_in_zip(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_v2_product(Path(td), ui_in_zip=False)
            self.assertTrue(any("zip 内缺 UI 入口" in e for e in verify_product(pdir, index)))

    def test_v2_ui_entry_path_escape(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(ui_entry="../evil.json", logic_sha256="0" * 64)
            pdir, index = make_v2_product(Path(td), manifest=m, ui_in_zip=False)
            self.assertTrue(any("ui.entry 路径非法" in e for e in verify_product(pdir, index)))

    def test_v2_ui_entry_unparsable(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_v2_product(Path(td), ui_text="{not json")
            self.assertTrue(any("UI 入口不可解析" in e for e in verify_product(pdir, index)))

    def test_v2_ui_document_structural_errors(self):
        cases = {
            "schema": ({"schema": "shadeling-ui/9", "version": 1,
                        "root": ui_doc()["root"]}, "schema 必须为 shadeling-ui/1"),
            "version": ({"schema": "shadeling-ui/1", "version": "1",
                         "root": ui_doc()["root"]}, "version 必须为整数"),
            "no_root": ({"schema": "shadeling-ui/1", "version": 1}, "缺 root 节点"),
            "leaf_root": ({"schema": "shadeling-ui/1", "version": 1,
                           "root": {"type": "text", "id": "root"}}, "root 必须为容器类节点"),
            "unknown_type": (ui_doc({"type": "container", "id": "root", "children": [
                {"type": "chart", "id": "c1"}]}), "节点类型不在白名单"),
            "bad_id": (ui_doc({"type": "container", "id": "Root", "children": [
                {"type": "text", "id": "ok"}]}), "节点 id 非法"),
            "leaf_children": (ui_doc({"type": "container", "id": "root", "children": [
                {"type": "text", "id": "t", "children": []}]}), "叶子节点不得携带 children"),
            "too_deep": (ui_doc(deep_root(16)), "嵌套深度超上限"),
        }
        for label, (doc, expect) in cases.items():
            with self.subTest(case=label):
                errs = verify_ui_document(doc)
                self.assertTrue(any(expect in e for e in errs), f"{label}: {errs}")

    # ② 无裸弹层调用

    def test_v2_bare_overlay_rejected(self):
        for bare in ("sheet", "dialog", "alert", "confirm", "modal", "toast"):
            with self.subTest(bare=bare):
                doc = ui_doc({"type": "container", "id": "root", "children": [
                    {"type": bare, "id": "pop"}]})
                errs = verify_ui_document(doc)
                self.assertTrue(any("裸弹层调用" in e for e in errs), errs)

    def test_v2_overlay_node_accepted(self):
        doc = ui_doc({"type": "container", "id": "root", "children": [
            {"type": "overlay", "id": "confirm",
             "props": {"kind": "dialog", "title": "确认", "message": "删除？"}}]})
        self.assertEqual(verify_ui_document(doc), [])

    def test_v2_overlay_bad_subtype(self):
        doc = ui_doc({"type": "container", "id": "root", "children": [
            {"type": "overlay", "id": "confirm", "props": {"kind": "popover"}}]})
        self.assertTrue(any("overlay 节点子类型非法" in e for e in verify_ui_document(doc)))

    def test_v2_bare_overlay_entry_fails_in_product(self):
        with tempfile.TemporaryDirectory() as td:
            ui = ui_doc({"type": "container", "id": "root", "children": [
                {"type": "sheet", "id": "pop"}]})
            pdir, index = make_v2_product(Path(td), ui=ui)
            self.assertTrue(any("裸弹层调用" in e for e in verify_product(pdir, index)))

    # ③ logic.entry 已签名或哈希登记

    def test_v2_missing_logic_section(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_entry=None)
            del m["logic"]
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("缺 logic 段" in e for e in verify_product(pdir, index)))

    def test_v2_missing_logic_entry(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_entry=None, logic_sha256="0" * 64)
            pdir, index = make_v2_product(Path(td), manifest=m, logic_in_zip=False)
            self.assertTrue(any("缺 logic.entry" in e for e in verify_product(pdir, index)))

    def test_v2_logic_entry_absent_in_zip(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_v2_product(Path(td), logic_in_zip=False)
            self.assertTrue(any("zip 内缺 logic.entry" in e for e in verify_product(pdir, index)))

    def test_v2_logic_unregistered(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest()  # 既无 sha256 也无 signature
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("未登记哈希或签名" in e for e in verify_product(pdir, index)))

    def test_v2_logic_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_sha256="a" * 64)
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("哈希不一致" in e for e in verify_product(pdir, index)))

    def test_v2_logic_signature_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_signature="shadeling-sig/v1:" + "b" * 64)
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertEqual(verify_product(pdir, index), [])

    def test_v2_logic_signature_bad_format(self):
        with tempfile.TemporaryDirectory() as td:
            m = make_v2_manifest(logic_signature="TODO-sign-me")
            pdir, index = make_v2_product(Path(td), manifest=m)
            self.assertTrue(any("signature 格式非法" in e for e in verify_product(pdir, index)))

    def test_v2_inner_manifest_ui_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            pdir, index = make_v2_product(Path(td))
            patch_inner_manifest(pdir, index, lambda inner: inner.pop("ui"))
            errs = verify_product(pdir, index)
            self.assertTrue(any("不一致：ui=" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
