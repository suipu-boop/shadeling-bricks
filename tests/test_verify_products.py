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
        "download_url": f"https://example.com/{name}-{version}.zip",
        "sha256": "0" * 64,
    }
    m.update(overrides)
    return m


def make_product(vault: Path, name="demo", version="1.0.0", manifest=None):
    """构造 products/<name>/ 目录：manifest + releases zip + index 登记。"""
    pdir = vault / "products" / name
    rel = pdir / "releases" / version
    rel.mkdir(parents=True, exist_ok=True)
    zip_path = rel / f"{name}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("payload.txt", "hello")
    if manifest is None:
        manifest = make_manifest(name=name, version=version)
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


if __name__ == "__main__":
    unittest.main()
