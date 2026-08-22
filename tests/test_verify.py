#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证闸门自动化测试：契约/元数据/files/index/composition 五类校验。

隔离策略：全部用例在临时目录（tempfile.mkdtemp）内构造积木库，
不触碰真实 bricks/ 与 index.json。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify_bricks import verify_brick  # noqa: E402


def make_brick_dir(vault: Path, name: str, brick: dict, files: dict = None,
                   index_entry: dict = None, all_names: set = None):
    """在临时 vault 中构造一个积木目录 + 实现文件 + index 登记。"""
    brick_dir = vault / "bricks" / name
    brick_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in (files or {}).items():
        fpath = brick_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    (brick_dir / "brick.json").write_text(
        json.dumps(brick, ensure_ascii=False), encoding="utf-8")
    if index_entry is not None:
        entries = [index_entry]
    else:
        entries = [{k: brick.get(k) for k in
                    ("name", "version", "category", "risk_level", "summary")}]
        entries[0]["path"] = f"bricks/{name}/"
    index = {"bricks": entries}
    return brick_dir, index


def valid_brick(name="demo"):
    return {
        "name": name,
        "summary": "测试积木",
        "version": "0.1.0",
        "category": "tool",
        "risk_level": "low",
        "author": "tester",
        "description": "用于测试",
        "tags": ["test"],
        "license": "MIT",
        "source": "local",
        "capabilities": ["run"],
        "dependencies": [],
        "composition": {},
        "resources": {"memory_mb": 64, "disk_mb": 10, "ports": [], "network": False},
        "files": [{"src": "src/main.py", "kind": "python"}],
    }


class TestVerifyBrick(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vault-test-")
        self.vault = Path(self._tmp)

    def _mk(self, name="demo", brick=None, files=None, index_entry=None, all_names=None):
        brick = brick if brick is not None else valid_brick(name)
        return make_brick_dir(self.vault, name, brick, files, index_entry, all_names)

    # —— 通过场景 ——
    def test_valid_brick_passes(self):
        brick_dir, index = self._mk(files={"src/main.py": "print('hi')"})
        errs = verify_brick(brick_dir, index, set(), strict=True)
        self.assertEqual(errs, [], f"合法积木不应报错：{errs}")

    def test_valid_brick_relaxed_mode_passes_without_extra_meta(self):
        brick = valid_brick()
        del brick["author"]
        del brick["description"]
        del brick["tags"]
        del brick["license"]
        del brick["source"]
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertEqual(errs, [], f"宽松模式不应要求扩展元数据：{errs}")

    def test_strict_mode_requires_extra_meta(self):
        brick = valid_brick()
        del brick["author"]
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=True)
        self.assertTrue(any("author" in e for e in errs), f"严格模式应报缺 author：{errs}")

    # —— 5 字段契约 ——
    def test_invalid_risk_level_fails(self):
        brick = valid_brick()
        brick["risk_level"] = "extreme"
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("risk_level" in e for e in errs), f"应报 risk_level 非法：{errs}")

    def test_invalid_capabilities_fails(self):
        brick = valid_brick()
        brick["capabilities"] = "run"
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("capabilities" in e for e in errs), f"应报 capabilities 非法：{errs}")

    def test_invalid_dependency_type_fails(self):
        brick = valid_brick()
        brick["dependencies"] = [{"name": "dep", "type": "unknown"}]
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("dependencies" in e for e in errs), f"应报 dependencies 非法：{errs}")

    def test_invalid_resources_fails(self):
        brick = valid_brick()
        brick["resources"] = {"memory_mb": -1}
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("resources" in e for e in errs), f"应报 resources 非法：{errs}")

    # —— 元数据 ——
    def test_missing_name_fails(self):
        brick = valid_brick()
        del brick["name"]
        brick_dir, index = self._mk(name="demo", brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("name" in e for e in errs), f"应报缺 name：{errs}")

    # —— files 存在性 ——
    def test_missing_impl_file_fails(self):
        brick_dir, index = self._mk(files={})  # brick.json 声明 src/main.py 但未提供
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("src/main.py" in e or "files" in e for e in errs),
                        f"应报实现文件缺失：{errs}")

    # —— index 对齐 ——
    def test_index_mismatch_fails(self):
        brick = valid_brick()
        index_entry = {k: brick.get(k) for k in
                       ("name", "version", "category", "risk_level", "summary", "path")}
        index_entry["version"] = "9.9.9"  # 与 brick.json 不一致
        brick_dir, index = self._mk(files={"src/main.py": "x"}, index_entry=index_entry)
        errs = verify_brick(brick_dir, index, set(), strict=False)
        self.assertTrue(any("index" in e or "version" in e for e in errs),
                        f"应报 index 不一致：{errs}")

    # —— composition 引用 ——
    def test_composition_ref_missing_fails(self):
        brick = valid_brick()
        brick["composition"] = {"requires": ["not-exist"]}
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, {"demo"}, strict=False)
        self.assertTrue(any("not-exist" in e for e in errs),
                        f"应报引用的积木不存在：{errs}")

    def test_composition_ref_present_passes(self):
        brick = valid_brick()
        brick["composition"] = {"requires": ["other"]}
        brick_dir, index = self._mk(brick=brick, files={"src/main.py": "x"})
        errs = verify_brick(brick_dir, index, {"demo", "other"}, strict=False)
        self.assertEqual(errs, [], f"引用的积木存在则不应报错：{errs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
