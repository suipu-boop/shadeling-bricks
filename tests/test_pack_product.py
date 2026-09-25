#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品积木出包收尾脚本自动化测试（市场 V2）。

隔离策略：monkeypatch pack_product 的 PRODUCTS_DIR / INDEX_PATH 到临时目录，
不触碰真实 products/ 与 index.json。
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import pack_product  # noqa: E402
from test_verify_products import make_manifest, zip_manifest  # noqa: E402


class PackProductTest(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.vault = Path(self._td.name)
        self.products = self.vault / "products"
        self.index_path = self.vault / "index.json"
        self.products.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps({"schema": "brick-registry/v1+v2", "products": [],
                        "updated_at": "2000-01-01T00:00:00"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        self._patches = [
            mock.patch.object(pack_product, "PRODUCTS_DIR", self.products),
            mock.patch.object(pack_product, "INDEX_PATH", self.index_path),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._td.cleanup()

    # —— helpers ——

    def _url(self, name, version):
        return (f"https://github.com/suipu-boop/shadeling-bricks/raw/main/"
                f"products/{name}/releases/{version}/{name}-{version}.zip")

    def _write_manifest(self, name="demo", version="1.0.0", **overrides):
        m = make_manifest(name=name, version=version, bundle="Demo.app")
        m["download_url"] = self._url(name, version)
        m["sha256"] = ""
        m.update(overrides)
        pdir = self.products / name
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return m

    def _write_zip(self, name="demo", version="1.0.0", with_manifest=True):
        rel = self.products / name / "releases" / version
        rel.mkdir(parents=True, exist_ok=True)
        zip_path = rel / f"{name}-{version}.zip"
        m = json.loads((self.products / name / "manifest.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("Demo.app/Contents/Info.plist", "<plist/>")
            if with_manifest:
                zf.writestr("manifest.json", json.dumps(zip_manifest(m), ensure_ascii=False))
        return zip_path

    # —— stage ——

    def test_stage_strips_release_metadata(self):
        self._write_manifest()
        out = self.vault / "dist" / "manifest.json"
        pack_product.stage("demo", out)
        inner = json.loads(out.read_text(encoding="utf-8"))
        self.assertNotIn("sha256", inner)
        self.assertNotIn("download_url", inner)
        self.assertEqual(inner["id"], "com.shadeling.brick.demo")
        self.assertEqual(inner["bundle"], "Demo.app")

    def test_stage_rejects_name_dir_mismatch(self):
        self._write_manifest(name="demo")
        m = json.loads((self.products / "demo" / "manifest.json").read_text(encoding="utf-8"))
        m["name"] = "other"
        (self.products / "demo" / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(pack_product.PackError):
            pack_product.stage("demo", self.vault / "dist" / "manifest.json")

    # —— finalize ——

    def test_finalize_backfills_manifest_and_index(self):
        self._write_manifest()
        zip_path = self._write_zip()
        pack_product.finalize("demo", "1.0.0")

        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        m = json.loads((self.products / "demo" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["sha256"], digest)
        self.assertEqual((zip_path.parent / (zip_path.name + ".sha256")).read_text(encoding="utf-8"),
                         f"{digest}  {zip_path.name}\n")
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        entry = index["products"][0]
        self.assertEqual(entry["sha256"], digest)
        self.assertEqual(entry["download_url"], m["download_url"])
        self.assertNotEqual(index["updated_at"], "2000-01-01T00:00:00")

    def test_finalize_keeps_other_index_entries(self):
        self.index_path.write_text(json.dumps(
            {"products": [{"name": "other", "version": "0.1.0", "sha256": "x"}]},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._write_manifest()
        self._write_zip()
        pack_product.finalize("demo", "1.0.0")
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.assertEqual([e["name"] for e in index["products"]], ["other", "demo"])

    def test_finalize_rejects_zip_without_manifest(self):
        self._write_manifest()
        self._write_zip(with_manifest=False)
        with self.assertRaises(pack_product.PackError) as ctx:
            pack_product.finalize("demo", "1.0.0")
        self.assertIn("zip 内缺 manifest.json", str(ctx.exception))

    def test_finalize_rejects_wrong_download_url(self):
        self._write_manifest()
        m = json.loads((self.products / "demo" / "manifest.json").read_text(encoding="utf-8"))
        m["download_url"] = "https://example.com/wrong.zip"
        (self.products / "demo" / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        self._write_zip()
        with self.assertRaises(pack_product.PackError) as ctx:
            pack_product.finalize("demo", "1.0.0")
        self.assertIn("download_url", str(ctx.exception))

    def test_finalize_rejects_version_drift(self):
        self._write_manifest(version="1.0.0")
        self._write_zip()
        with self.assertRaises(pack_product.PackError):
            pack_product.finalize("demo", "1.0.1")

    def test_finalize_then_verify_passes(self):
        """闭环：出包收尾后的产物必须能过发布闸门。"""
        from verify_products import verify_product
        self._write_manifest()
        self._write_zip()
        pack_product.finalize("demo", "1.0.0")
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.assertEqual(verify_product(self.products / "demo", index), [])


if __name__ == "__main__":
    unittest.main()
