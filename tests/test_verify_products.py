#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品积木发布闸门自动化测试（市场 V2）。

隔离策略：全部用例在临时目录（tempfile.mkdtemp）内构造产品库，
不触碰真实 products/ 与 index.json。
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify_products import verify_product  # noqa: E402


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
            zf.writestr("Demo.app/Contents/Info.plist", "<plist/>")
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


if __name__ == "__main__":
    unittest.main()
