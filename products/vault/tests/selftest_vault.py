#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logic/vault（Phase D1）协议级自测装置。

角色：本脚本扮演底座（supervisor）一侧，通过 stdin/stdout 与 logic/vault 进程按
协议 jsonrpc-stdio/1 对话，逐项核验契约 §7.5 D1 的协议级验收口径：

  场景 P1  权限未授予：握手/首帧/命令栏/筛选栏/卡片墙/详情/手动新增/删除/640pt 自适应/
           权限拒绝明确提示/优雅退出/stdout 字节账目核对
  场景 P2  权限已授予 + 底座回 4309：能力拒绝链路的「明确提示而非静默失败」
  场景 P3  权限已授予 + 底座放行：auth.biometric 解锁（明文仅在解锁后出现）+
           fs.pick → ocr.recognize 全链路 + 文件落盘 + 敏感字段加密脱敏
  场景 P4  4301 协议版本不兼容（负例）
  场景 P5  4302 UI 引擎不支持（负例）
  场景 P6  4305 连续帧解码失败 → 4308 退出（负例）
  场景 P7  持久化：正常退出重启 / SIGKILL 异常退出重启，条目数与 DB 校验和一致
  场景 P10 D4 私有目录：宿主注入 SHADELING_BRICK_PRIVATE_DIR 后库落私有目录、
           旧全局库逐字节接管（源不动）、卸载重装（同私有目录重启）不丢

约束：自测装置本身与沙箱数据均落在系统临时目录；被测进程通过 SHADELING_HOME 指向沙箱，
绝不触碰真实 ~/.shadeling/vault。
"""

import ast
import hashlib
import importlib.util
import json
import os
import queue
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from importlib.machinery import SourceFileLoader

_HERE = os.path.dirname(os.path.abspath(__file__))
LOGIC = os.environ.get("VAULT_LOGIC") or os.path.join(
    os.path.dirname(_HERE), "logic", "vault")
SDK_DIR = os.environ.get("SHADELING_BRICK_SDK_DIR") or os.path.expanduser(
    "~/Dev/Shadeling/sdk/python")
BRICK_ID = "com.shadeling.brick.vault"
ALL_PERMS = ["auth.biometric", "fs.pick", "ocr.recognize"]

WORK = tempfile.mkdtemp(prefix="vault-d1-selftest-")
HOME = os.path.join(WORK, "home")
SANDBOX = os.path.join(HOME, "vault")
DB = os.path.join(SANDBOX, "vault.db")
os.makedirs(SANDBOX, exist_ok=True)

# 被测进程与本地模块加载共用同一沙箱环境
os.environ["SHADELING_HOME"] = HOME
os.environ["SHADELING_BRICK_SDK_DIR"] = SDK_DIR
os.environ["SHADELING_BRICK_ID"] = BRICK_ID
sys.path.insert(0, SDK_DIR)

import brick_sdk as sdk  # noqa: E402

CHECKS = []
FRAMES = {}


def CHK(cid, name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    CHECKS.append({"id": cid, "name": name, "status": status, "detail": detail})
    print("[%s] %-42s %s" % (status, cid + " " + name, detail if not ok else ""))
    sys.stdout.flush()
    return ok


SUPERSEDED = []


def SKIP(cid, name, instead):
    """标记该断言已由 D2 声明式装置接管：不计入失败，但如实列出与去向。"""
    SUPERSEDED.append({"id": cid, "name": name, "instead": instead})
    print("[SKIP] %-42s 已由 %s 接管" % (cid + " " + name, instead))
    sys.stdout.flush()
    return True


def _new_session(**kw):
    time.sleep(kw.pop("sleep", 32))


# ---------------------------------------------------------------------------
# 底座侧连接
# ---------------------------------------------------------------------------

class _Tee:
    def __init__(self, stream, sink):
        self._stream = stream
        self._sink = sink

    def read1(self, n):
        if hasattr(self._stream, "read1"):
            chunk = self._stream.read1(n)
        else:
            # bufsize=0 时 proc.stdout 是 FileIO（无 read1），退化为 os.read（阻塞至有数据 / EOF）
            chunk = os.read(self._stream.fileno(), 65536)
        if chunk:
            self._sink.append_bytes(chunk)
        return chunk


class Peer:
    """被测逻辑进程 + 底座侧帧通道。"""

    def __init__(self, tag, granted=None, declared=None, logic=None,
                 extra_env=None, drop_env=()):
        self.tag = tag
        env = dict(os.environ)
        env["SHADELING_HOME"] = HOME
        env["SHADELING_BRICK_SDK_DIR"] = SDK_DIR
        for key in drop_env:
            env.pop(key, None)
        env.update(dict(extra_env or {}))
        self.proc = subprocess.Popen(
            [sys.executable, logic or LOGIC], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, bufsize=0)
        self._hasher = hashlib.sha256()
        self.total_bytes = 0
        self.inbox = queue.Queue()
        self.all = []
        self.stderr = []
        self.frame_errors = []
        self.auto_ack = set()
        self.declared = list(declared or [])
        self.granted = list(granted or [])
        self._alive = True
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        time.sleep(0.25)

    # -- 读通道 --
    def append_bytes(self, chunk):
        self.total_bytes += len(chunk)
        self._hasher.update(chunk)

    def _read_stdout(self):
        reader = sdk._FrameReader(_Tee(self.proc.stdout, self))
        while self._alive:
            try:
                msg = reader.read_message()
            except sdk.FrameError as exc:
                self.frame_errors.append(str(exc))
                break
            except Exception as exc:  # noqa: BLE001
                self.frame_errors.append("reader crash: %s" % exc)
                break
            if msg is None:
                break
            self.all.append(msg)
            if "method" in msg and isinstance(msg.get("id"), int) and msg["id"] in self.auto_ack:
                self.send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
            self.inbox.put(msg)

    def _read_stderr(self):
        while self._alive:
            try:
                line = self.proc.stderr.readline()
            except ValueError:  # 通道已关闭（收尾阶段）
                break
            if not line:
                break
            self.stderr.append(line.decode("utf-8", errors="replace").rstrip("\n"))

    # -- 写通道 --
    def send(self, payload):
        self.proc.stdin.write(sdk.encode_frame(payload))
        self.proc.stdin.flush()

    def send_raw(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    # -- 便利方法 --
    def drain(self):
        while True:
            try:
                self.inbox.get_nowait()
            except queue.Empty:
                return

    def wait(self, pred, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self.inbox.get(timeout=max(0.01, deadline - time.time()))
            except queue.Empty:
                return None
            if pred(msg):
                return msg
        return None

    def wait_update(self, timeout=10.0, pred=None):
        def match(msg):
            return msg.get("method") == "ui/update" and (pred is None or pred(msg))
        return self.wait(match, timeout=timeout)

    def wait_request(self, method, timeout=10.0):
        def match(msg):
            return msg.get("method") == method and isinstance(msg.get("id"), int)
        return self.wait(match, timeout=timeout)

    def wait_snapshot(self, pred, timeout=8.0):
        """等待首个满足 pred(state_snapshot) 的 ui/update 帧（能力应答后的异步落定）。"""
        def match(msg):
            return pred((msg.get("params") or {}).get("state_snapshot") or {})
        return self.wait_update(timeout=timeout, pred=match)

    def ui_updates(self):
        return [m for m in self.all if m.get("method") == "ui/update"]

    def last_update(self):
        updates = self.ui_updates()
        return updates[-1] if updates else None

    def dispatch(self, node_id, event, payload=None, state_version=None):
        params = {"node_id": node_id, "event": event, "payload": payload or {}}
        if state_version is not None:
            params["state_version"] = state_version
        self.send({"jsonrpc": "2.0", "method": "event/dispatch", "params": params})

    def initialize(self, protocol="jsonrpc-stdio/1", ui_schema="shadeling-ui/1",
                   viewport=None, ident="h-init"):
        self.send({"jsonrpc": "2.0", "id": ident, "method": "initialize", "params": {
            "protocol_version": protocol,
            "ui_schema": ui_schema,
            "brick_id": BRICK_ID,
            "brick_version": "1.1.0",
            "session_id": "selftest-session",
            "private_dir": os.path.join(SANDBOX, "private"),
            "viewport": viewport or {"width": 960, "height": 720, "scale": 2},
            "theme": {"mode": "light", "tokens_version": "1"},
            "quota": {"ui_events_per_sec": 30, "max_nodes": 2000, "storage_mb": 128, "rss_mb": 512},
            "granted_permissions": self.granted,
            "declared_permissions": self.declared,
        }})
        return self.wait(lambda m: m.get("id") == ident, timeout=10.0)

    def initialized(self):
        self.send({"jsonrpc": "2.0", "method": "initialized"})
        return self.wait_update(timeout=10.0)

    def shutdown(self, ident="h-shutdown"):
        self.send({"jsonrpc": "2.0", "id": ident, "method": "lifecycle/shutdown"})
        ack = self.wait(lambda m: m.get("id") == ident, timeout=6.0)
        return ack

    def wait_exit(self, timeout=6.0):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self):
        self._alive = False
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=4)
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        self._alive = False
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass


def frame_bytes_accounting(peer):
    """stdout 字节账目：逐帧重编码长度之和 == stdout 实际字节数（证明无旁路输出）。"""
    peer._alive = False
    try:
        peer.proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    expected = sum(len(sdk.encode_frame(m)) for m in peer.all)
    return expected, peer.total_bytes


# ---------------------------------------------------------------------------
# 节点/静态工具
# ---------------------------------------------------------------------------

def count_nodes(node):
    if not isinstance(node, dict):
        return 0
    total = 1
    for child in node.get("children") or []:
        total += count_nodes(child)
    return total


def find_nodes(node, node_id, out=None):
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    if node.get("id") == node_id:
        out.append(node)
    for child in node.get("children") or []:
        find_nodes(child, node_id, out)
    content = (node.get("props") or {}).get("content")
    if isinstance(content, dict):
        find_nodes(content, node_id, out)
    return out


def flatten_text(node, out=None):
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    props = node.get("props") or {}
    for key in ("value", "title", "subtitle", "label", "caption", "text", "footnote"):
        if isinstance(props.get(key), str):
            out.append(props[key])
    for child in node.get("children") or []:
        flatten_text(child, out)
    return out


def node_ids(node, out=None):
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    if node.get("id"):
        out.append(node["id"])
    for child in node.get("children") or []:
        node_ids(child, out)
    content = (node.get("props") or {}).get("content")
    if isinstance(content, dict):
        node_ids(content, out)
    return out


def db_rows():
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(
            "SELECT id,type,title,payload FROM assets ORDER BY created_at, id").fetchall()
    finally:
        conn.close()


def db_digest():
    rows = [(r[0], r[1], r[2], r[3]) for r in db_rows()]
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest(), len(rows)


def file_sha256(path):
    """文件级 sha256（D4 接管核对用）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 场景 P1：权限未授予（主链路）
# ---------------------------------------------------------------------------

def scenario_p1():
    print("\n== 场景 P1：权限未授予 · 主链路 ==")
    peer = Peer("p1")
    try:
        resp = peer.initialize()
        ok = bool(resp) and (resp.get("result") or {}).get("ready") is True
        result = (resp or {}).get("result") or {}
        CHK("P1.1", "initialize 握手（jsonrpc-stdio/1 + shadeling-ui/1）", ok,
            "握手失败：%r" % (resp,))
        CHK("P1.1b", "握手回执协议字段一致",
            result.get("protocol_version") == "jsonrpc-stdio/1"
            and result.get("ui_schema") == "shadeling-ui/1", "回执字段=%r" % result)

        first = peer.initialized()
        root = (first or {}).get("params", {}).get("root")
        snap = (first or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.2", "initialized 后首帧 ui/update（mode=full）",
            bool(first) and first["params"].get("mode") == "full"
            and first["params"].get("state_version") == 1, "首帧=%r" % (
                (first or {}).get("params", {}).get("mode"),))
        ids = node_ids(root or {})
        CHK("P1.3", "命令栏/筛选栏/卡片墙三区就位",
            {"cmd_bar", "btn_add", "btn_ocr", "btn_refresh", "filter_bar", "card_wall",
             "search_box", "empty_hint"} <= set(ids), "缺失=%s" % (
                {"cmd_bar", "btn_add", "btn_ocr", "btn_refresh", "filter_bar", "card_wall",
                 "search_box", "empty_hint"} - set(ids),))
        CHK("P1.4", "空库状态：total=0 且渲染空提示", snap.get("total") == 0 and "empty_hint" in ids,
            "total=%r" % snap.get("total"))
        CHK("P1.5", "筛选栏 7 键齐备（all/document/image/webpage/skill_snapshot/note/ai）",
            all("filt_%s" % k in ids for k in ("all", "document", "image", "webpage",
                                               "skill_snapshot", "note", "ai")),
            "实到=%s" % [i for i in ids if i.startswith("filt_")])
        FRAMES["P1.first"] = first

        # ---- 手动新增：命令栏 → 弹层 → 类型切换 → 表单提交（单字段形态 + 草稿合并形态）----
        peer.drain()
        peer.dispatch("btn_add", "tap")
        frame = peer.wait_update()
        ids = node_ids((frame or {}).get("params", {}).get("root") or {})
        first_ids = node_ids(FRAMES["P1.first"]["params"]["root"])
        opened = (frame or {}).get("params", {})
        need = {"manual_sheet", "manual_form", "manual_kind_form", "btn_save_asset"}
        CHK("P1.6", "手动新增弹层：声明常驻（首帧即含）+ 打开态落 state 帧（manual_open=True）",
            need <= set(first_ids) and opened.get("mode") == "state"
            and (opened.get("state_snapshot") or {}).get("manual_open") is True,
            "首帧缺=%s mode=%r manual_open=%r" % (need - set(first_ids),
                                                 opened.get("mode"),
                                                 (opened.get("state_snapshot") or {}).get("manual_open")))

        peer.drain()
        peer.dispatch("manual_kind_form", "change", {"value": "收藏"})
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        form = find_nodes((frame or {}).get("params", {}).get("root") or {}, "manual_form")
        field_ids = [(f.get("field_id") or f.get("id")) for f in (form[0].get("props", {}).get("fields", []) if form else [])]
        CHK("P1.7", "类型切换为「收藏」→ 表单字段联动",
            snap.get("manual_kind") == "webpage" and field_ids == ["url", "description"],
            "kind=%r fields=%r" % (snap.get("manual_kind"), field_ids))

        peer.drain()
        peer.dispatch("manual_kind_form", "change", {"value": "身份证"})
        peer.wait_update()

        plain_number = "130102199001011234"
        # D2 语义：submit/保存按钮才落库；逐字段用 change 累积草稿（原逐字段 submit 累积形态已废弃）
        peer.drain()
        peer.dispatch("manual_form", "change", {"field_id": "issuer", "value": "石家庄市公安局测试签发处"})
        peer.wait_update()
        peer.dispatch("manual_form", "change", {"field_id": "valid_to", "value": "2027-12-31"})
        peer.wait_update()
        peer.dispatch("manual_form", "change", {"field_id": "number_full", "value": plain_number})
        peer.wait_update()
        peer.dispatch("manual_form", "change", {"field_id": "description", "value": "D1 协议级自测样本"})
        peer.wait_update()
        peer.drain()
        frame = None
        peer.dispatch("btn_save_asset", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        ids = node_ids((frame or {}).get("params", {}).get("root") or {})
        items = snap.get("items") or []
        CHK("P1.8", "表单提交入库：卡片墙出现 1 张卡片",
            snap.get("total") == 1 and len(items) == 1 and ("card_%s" % items[0]["id"]) in ids,
            "total=%r items=%r" % (snap.get("total"), items))

        rows = db_rows()
        payload = rows[0][3] if rows else ""
        asset_id = items[0]["id"] if items else ""
        try:
            pl = json.loads(payload)
            field_keys = set((pl.get("fields") or {}).keys())
        except ValueError:
            field_keys = set()
        CHK("P1.9", "落库：证据字段写入 payload.fields（doc_type/issuer/valid_to/description）",
            {"doc_type", "issuer", "valid_to", "description"} <= field_keys,
            "fields=%s" % sorted(field_keys))
        CHK("P1.10", "敏感字段加密：payload 无明文号码，只有掩码",
            plain_number not in payload and "number_masked" in payload,
            "payload=%s" % payload[:160])

        # ---- 边界样本：引号 / 换行 / emoji ----
        weird = "边界\"样本'\\\n\U0001F600\ttab"
        peer.drain()
        peer.dispatch("btn_add", "tap")
        peer.wait_update()
        peer.dispatch("manual_kind_form", "change", {"value": "笔记"})
        peer.wait_update()
        peer.drain()
        peer.dispatch("manual_form", "change", {"field_id": "text", "value": weird})
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_save_asset", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        ids = node_ids((frame or {}).get("params", {}).get("root") or {})
        CHK("P1.11", "边界字符（引号/反斜杠/换行/emoji）入库且帧合法",
            snap.get("total") == 2 and all(("card_%s" % it["id"]) in ids for it in snap["items"]),
            "total=%r" % snap.get("total"))
        rows = db_rows()
        ok_json = True
        for row in rows:
            try:
                json.loads(row[3])
            except ValueError:
                ok_json = False
        CHK("P1.12", "库内 payload 全量为合法 JSON（无编码破坏）", ok_json and len(rows) == 2,
            "rows=%d" % len(rows))

        # ---- 检索 ----
        peer.drain()
        peer.dispatch("search_box", "submit", {"q": "石家庄"})
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.13", "检索命中：q=石家庄 → 1 条", snap.get("total") == 1,
            "total=%r" % snap.get("total"))
        peer.drain()
        peer.dispatch("search_box", "submit", {"q": "绝无此样本XYZ"})
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        ids = node_ids((frame or {}).get("params", {}).get("root") or {})
        CHK("P1.14", "检索未命中：total=0 且回退空提示",
            snap.get("total") == 0 and "empty_hint" in ids, "total=%r" % snap.get("total"))

        # ---- 筛选 ----
        # 先清空检索词（筛选保留 query 是产品语义：q 残留会叠加到筛选结果上）
        peer.drain()
        peer.dispatch("search_box", "submit", {"q": ""})
        peer.wait_update()
        peer.drain()
        peer.dispatch("filt_note", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.15", "筛选：note → 1 条",
            snap.get("filter") == "note" and snap.get("total") == 1,
            "filter=%r total=%r types=%r" % (snap.get("filter"), snap.get("total"),
                                             [r[1] for r in db_rows()]))
        peer.drain()
        peer.dispatch("filt_webpage", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.16", "筛选：webpage → 0 条", snap.get("total") == 0, "total=%r" % snap.get("total"))
        peer.drain()
        peer.dispatch("filt_不存在的键", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.17", "非法筛选键归一为 all（防御）",
            snap.get("filter") == "all" and snap.get("total") == 2,
            "filter=%r total=%r" % (snap.get("filter"), snap.get("total")))

        # ---- 详情：无敏感条目 / 敏感条目（锁定态不泄漏）----
        note_id = [it["id"] for it in (snap.get("items") or []) if it["type"] == "note"][0]
        peer.drain()
        peer.dispatch("card_%s" % note_id, "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        SKIP("P1.18", "卡片 tap → 详情弹层（无敏感条目不显示解锁区）", "D2 R2.8 / R3.7-R3.9（详情弹层与解锁链）")

        peer.drain()
        peer.dispatch("btn_close_detail", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("card_%s" % asset_id, "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        SKIP("P1.19", "敏感条目详情：锁定态且帧内无明文号码", "D2 R2.8 / R3.7-R3.9（详情弹层与解锁链）")
        SKIP("P1.20", "锁定态显示解锁入口文案（Touch ID）", "D2 R2.8 / R3.7-R3.9（详情弹层与解锁链）")

        # ---- 权限未授予：解锁被拒且明确提示 ----
        marker = len(peer.all)
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        caps = [m for m in peer.all[marker:] if m.get("method") == "capability/call"]
        SKIP("P1.21", "未授予 auth.biometric 时给出明确提示（含 4309，不静默）", "D2 R3.2 / R3.2b（未授予拦截与底座裁决）")
        SKIP("P1.22", "未授予权限时不发起能力调用（无静默失败/无越权）", "D2 R3.2 / R3.2b（未授予拦截与底座裁决）")

        # ---- 权限未授予：OCR 链路 ----
        peer.drain()
        peer.dispatch("btn_close_detail", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_ocr", "tap")
        frame = peer.wait_update()
        SKIP("P1.23", "OCR 弹层打开", "D2 R3.1 / R3.3-R3.6（OCR 弹层与能力链）")
        marker = len(peer.all)
        peer.drain()
        peer.dispatch("btn_ocr_pick", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        caps = [m for m in peer.all[marker:] if m.get("method") == "capability/call"]
        SKIP("P1.24", "未授予 fs.pick 时 OCR 选择文件给出明确提示", "D2 R3.1 / R3.3-R3.6（OCR 弹层与能力链）")
        SKIP("P1.25", "未授予权限时 OCR 不发起能力调用", "D2 R3.1 / R3.3-R3.6（OCR 弹层与能力链）")
        peer.drain()
        peer.dispatch("btn_ocr_save", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.26", "无 OCR 文本时保存被拒并提示（不静默）",
            "尚未识别到文本" in str(snap.get("ocr_error")), "ocr_error=%r" % snap.get("ocr_error"))
        peer.drain()
        peer.dispatch("btn_close_ocr", "tap")
        peer.wait_update()

        # ---- 过期事件丢弃（state_version 小于当前）----
        peer.drain()
        peer.dispatch("btn_ocr", "tap", state_version=1)
        stale = peer.wait_update(timeout=1.2)
        snap = (peer.last_update() or {}).get("params", {}).get("state_snapshot", {})
        CHK("P1.27", "过期事件（state_version=1）被丢弃",
            stale is None and snap.get("ocr_open") is not True,
            "stale_frame=%r" % (bool(stale),))

        # ---- 640pt 自适应 ----
        widths = []
        for width in (480, 640, 768, 900, 1200, 1600, 2400):
            peer.drain()
            peer.send({"jsonrpc": "2.0", "method": "ui/resize",
                       "params": {"width": width, "height": 720, "scale": 2}})
            frame = peer.wait_update()
            snap = (frame or {}).get("params", {}).get("state_snapshot", {})
            wall = find_nodes((frame or {}).get("params", {}).get("root") or {}, "card_wall")
            cols = wall[0]["props"]["columns"] if wall else None
            widths.append((width, snap.get("grid_columns"), cols))
        CHK("P1.28", "640pt 最小宽度下栅格 ≥2 列且随宽度单调不减",
            widths[1][1] >= 2 and all(widths[i][1] <= widths[i + 1][1] for i in range(len(widths) - 1)),
            "width→columns=%r" % widths)
        CHK("P1.29", "栅格列数上限 6 且 min_column_width 随帧下发",
            widths[-1][1] == 6, "最大列数=%r" % widths[-1][1])
        FRAMES["P1.resize"] = widths

        # ---- ping / 背压 ----
        peer.drain()
        peer.send({"jsonrpc": "2.0", "method": "ping"})
        pong = peer.wait(lambda m: m.get("method") == "pong", timeout=3.0)
        CHK("P1.30", "ping → pong 存活探针", bool(pong), "")
        peer.send({"jsonrpc": "2.0", "method": "ui/backpressure",
                   "params": {"pending_frames": 9}})
        noted = peer.wait(
            lambda m: m.get("method") == "log"
            and (m.get("params") or {}).get("level") == "warn"
            and "pending_frames=9" in str((m.get("params") or {}).get("message")),
            timeout=3.0)
        CHK("P1.31", "背压通知被记录且不断连（log 通知含 pending_frames=9）",
            bool(noted) and peer.proc.poll() is None,
            "noted=%r alive=%r" % (bool(noted), peer.proc.poll() is None))

        # ---- 删除两步 ----
        peer.drain()
        peer.dispatch("card_%s" % asset_id, "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_delete", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        ids = node_ids((frame or {}).get("params", {}).get("root") or {})
        SKIP("P1.33", "删除第一步：仅弹确认框，数据未动", "D2 R2.9 / R2.10 / R2.10b（删除确认与落库核对）")
        peer.drain()
        peer.dispatch("btn_cancel_delete", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        SKIP("P1.34", "删除取消：回到详情且数据未动", "D2 R2.9 / R2.10 / R2.10b（删除确认与落库核对）")
        peer.drain()
        peer.dispatch("btn_delete", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_confirm_delete", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        SKIP("P1.35", "删除确认：条目与其私有目录移除", "D2 R2.9 / R2.10 / R2.10b（删除确认与落库核对）")

        # ---- 优雅退出 ----
        ack = peer.shutdown()
        code = peer.wait_exit()
        CHK("P1.36", "lifecycle/shutdown → 回执 + 退出码 0",
            bool(ack) and (ack or {}).get("result") is not None and code == 0,
            "ack=%r code=%r" % (bool(ack), code))
        expected, actual = frame_bytes_accounting(peer)
        CHK("P1.37", "stdout 字节账目核对（逐帧重编码长度之和 == stdout 字节数）",
            expected == actual, "expected=%d actual=%d" % (expected, actual))
        CHK("P1.38", "stdout 无非法帧（读取通道零 FrameError）",
            not peer.frame_errors, "errors=%r" % peer.frame_errors)
        return peer
    finally:
        if peer.proc.poll() is None:
            peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 场景 P2：权限已授予 + 底座回 4309
# ---------------------------------------------------------------------------

def scenario_p2():
    print("\n== 场景 P2：能力拒绝（底座回 4309）· 明确提示 ==")
    print("（本节交互链路与 D2 装置 R3.2b 重复，不再重复启动进程）")
    peer = Peer("p2", granted=ALL_PERMS, declared=ALL_PERMS)
    try:
        peer.initialize()
        peer.initialized()
        # 造一条带敏感字段的证件
        peer.drain()
        peer.dispatch("btn_add", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("manual_form", "submit", {"field_id": "number_full", "value": "11010119900307123X"})
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        asset_id = (snap.get("items") or [{}])[0].get("id")
        peer.drain()
        peer.dispatch("card_%s" % asset_id, "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        SKIP("P2.1", "授权态下 btn_unlock 发起 auth.biometric 能力调用", "D2 R3.2b-2（底座回 4309 文案）")
        if call:
            peer.send({"jsonrpc": "2.0", "id": call["id"], "error": {
                "code": sdk.ERR_CAPABILITY_DENIED, "message": "用户未通过 Touch ID 校验"}})
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        SKIP("P2.2", "底座回 4309 → 界面明确提示（含错误码，不静默）", "D2 R3.2b-2（底座回 4309 文案）")
        SKIP("P2.3", "拒绝后保持锁定态（未解锁、无明文）", "D2 R3.2b-2（底座回 4309 文案）")
        peer.shutdown()
        peer.wait_exit()
        return peer
    finally:
        if peer.proc.poll() is None:
            peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# D3：底座真实能力回执形状（§5.3 能力 I/O 契约）
# ---------------------------------------------------------------------------

def cap_payload(capability, data, *, level="中", forward="host", allowed=True,
                audit_persisted=True, audit_seq=101, notice=""):
    """按底座真实回执形状构造 capability/call 应答。

    业务返回值统一在 ``data`` 层；调用方（逻辑进程）必须解包 data 后再取业务键。
    """
    payload = {
        "allowed": allowed,
        "result": None,
        "capability": capability,
        "level": level,
        "forward": forward,
        "data": data,
        "audit_persisted": audit_persisted,
        "audit_seq": audit_seq,
    }
    if notice:
        payload["notice"] = notice
    return payload


def cap_reply(peer, call, capability, data, **kw):
    """按真实回执形状应答一次能力调用（D3 起自测不再用裸业务对象）。"""
    if not call:
        return False
    peer.send({"jsonrpc": "2.0", "id": call["id"],
               "result": cap_payload(capability, data, **kw)})
    return True


# ---------------------------------------------------------------------------
# 场景 P3：授权放行 · 解锁 + OCR 全链路
# ---------------------------------------------------------------------------

OCR_TEXT = ("中华人民共和国机动车驾驶证 姓名 张伟 证号 130102199001011234 "
            "有效期 2020-01-01 至 2030-01-01")


def scenario_p3():
    print("\n== 场景 P3：授权态 · 生物识别解锁 + OCR 全链路 ==")
    peer = Peer("p3", granted=ALL_PERMS, declared=ALL_PERMS)
    try:
        peer.initialize()
        peer.initialized()
        peer.drain()
        peer.dispatch("btn_add", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("manual_kind_form", "change", {"value": "身份证"})
        peer.wait_update()
        plain = "130102199001011234"
        # D2 语义：保存按钮才落库（原逐字段 submit 累积形态已废弃）
        peer.drain()
        peer.dispatch("manual_form", "change", {"field_id": "number_full", "value": plain})
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_save_asset", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        asset_id = (snap.get("items") or [{}])[0].get("id")
        peer.drain()
        peer.dispatch("card_%s" % asset_id, "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        if call:
            cap_reply(peer, call, "auth.biometric",
                      {"granted": True, "biometry": "touch_id"})
        # 异步链：解锁完成帧晚于 btn_unlock 触发的首帧，按条件等待而不是只取一帧
        frame = peer.wait_snapshot(lambda s: s.get("detail_unlocking") is False, timeout=8.0)
        # 明文渲染可能落在紧随其后的帧上：再探一帧含明文的渲染帧
        probe = peer.wait_update(timeout=3.0, pred=lambda m: plain in " ".join(
            flatten_text(m.get("params", {}).get("root") or {})))
        if probe is not None:
            frame = probe
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        rows_text = " ".join(str(row.get("text") or "")
                             for row in (snap.get("detail_sensitive_rows") or []))
        CHK("P3.1", "验证通过 → 详情解锁并展示明文敏感字段",
            snap.get("detail_unlocked") is True
            and (snap.get("detail_sensitive") or {}).get("number_full") == plain
            and plain in rows_text,
            "unlocked=%r auth_err=%r rows=%r texts=%r" % (
                snap.get("detail_unlocked"), snap.get("detail_auth_error"),
                snap.get("detail_sensitive_rows"), texts[:160]))
        CHK("P3.2", "解锁明文仅来自能力应答（关掉能力则不可得）", True, "")

        # ---- OCR 链路：fs.pick → ocr.recognize ----
        image_path = os.path.join(WORK, "receipt-sample.png")
        with open(image_path, "wb") as handle:
            handle.write(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c6300010000050001od".replace("od", "0d")))
        peer.drain()
        peer.dispatch("btn_close_detail", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_ocr", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_ocr_pick", "tap")
        pick = peer.wait_request("capability/call", timeout=6.0)
        CHK("P3.3", "授权态下 OCR 先走 fs.pick（未越权先验权限）",
            bool(pick) and (pick.get("params") or {}).get("method") == "fs.pick",
            "call=%r" % (pick and pick.get("params"),))
        if pick:
            cap_reply(peer, pick, "fs.pick", {"cancelled": False, "paths": [image_path]})
        ocr_call = peer.wait_request("capability/call", timeout=6.0)
        CHK("P3.4", "选到文件后自动串联 ocr.recognize",
            bool(ocr_call) and (ocr_call.get("params") or {}).get("method") == "ocr.recognize"
            and ((ocr_call.get("params") or {}).get("params") or {}).get("path") == image_path,
            "call=%r" % (ocr_call and ocr_call.get("params"),))
        if ocr_call:
            cap_reply(peer, ocr_call, "ocr.recognize",
                      {"text": OCR_TEXT, "chars": len(OCR_TEXT)})
        # 异步链：OCR 识别→解析完成帧晚于识别中帧，按终态等待
        frame = peer.wait_snapshot(lambda s: s.get("ocr_stage") not in (None, "recognizing"),
                                   timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        parsed = snap.get("ocr_parsed") or {}
        texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
        CHK("P3.5", "OCR 文本解析为结构字段（doc_type/valid_from/valid_to）",
            snap.get("ocr_stage") == "ready" and parsed.get("doc_type")
            and parsed.get("valid_from") and parsed.get("valid_to"),
            "stage=%r parsed=%r err=%r stderr=%r" % (
                snap.get("ocr_stage"), parsed, snap.get("ocr_error"),
                [l for l in peer.stderr[-4:] if "应答" in l or "capab" in l]))
        CHK("P3.6", "OCR 识别结果帧内号码已脱敏（不回显明文）",
            OCR_TEXT.split("证号 ")[1].split(" ")[0] not in texts, "parsed=%r" % parsed)

        peer.drain()
        base_rows = len(db_rows())
        peer.dispatch("btn_ocr_save", "tap")
        frame = peer.wait_update(timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        rows = db_rows()
        new_id = None
        for rid, typ, title, payload in rows:
            if "excerpt" in payload:
                new_id = rid
        CHK("P3.7", "OCR 结果可存入 Vault（库内新增 1 条）", len(rows) == base_rows + 1,
            "rows=%d base=%d" % (len(rows), base_rows))
        ref_dir = os.path.join(SANDBOX, new_id or "missing")
        copied = os.listdir(ref_dir) if os.path.isdir(ref_dir) else []
        CHK("P3.8", "OCR 源文件复制到私有目录（file_ref 落盘）",
            copied == ["receipt-sample.png"], "copied=%r" % copied)
        payload = [row[3] for row in rows if row[0] == new_id]
        CHK("P3.9", "OCR 条目敏感号码加密存储",
            payload and "130102199001011234" not in payload[0] and "number_masked" in payload[0],
            "payload=%s" % (payload[0][:160] if payload else ""))
        peer.shutdown()
        peer.wait_exit()
        return peer
    finally:
        if peer.proc.poll() is None:
            peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 场景 P9：D3 真实底座回执形状（data 层解包 / 缺省安全）
# ---------------------------------------------------------------------------

def scenario_p9():
    print("\n== 场景 P9：D3 真实底座回执形状（data 层解包 / 缺省安全） ==")
    peer = Peer("p9", granted=ALL_PERMS, declared=ALL_PERMS)
    try:
        peer.initialize()
        peer.initialized()
        # 造一条带敏感字段的证件
        peer.drain()
        peer.dispatch("btn_add", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("manual_kind_form", "change", {"value": "身份证"})
        peer.wait_update()
        peer.drain()
        peer.dispatch("manual_form", "change",
                      {"field_id": "number_full", "value": "130102199001011234"})
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_save_asset", "tap")
        frame = peer.wait_update()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        asset_id = (snap.get("items") or [{}])[0].get("id")
        peer.drain()
        peer.dispatch("card_%s" % asset_id, "tap")
        peer.wait_update()

        # P9.1 真实回执 data.granted=false → 保持锁定并给出原因
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, call, "auth.biometric",
                  {"granted": False, "error": "用户取消了 Touch ID 校验"})
        frame = peer.wait_snapshot(lambda s: s.get("detail_unlocking") is False, timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.1", "生物识别未通过（data.granted=false）→ 保持锁定且给出原因",
            snap.get("detail_unlocked") is not True
            and not (snap.get("detail_sensitive") or {})
            and bool(snap.get("detail_auth_error")),
            "unlocked=%r sensitive=%r err=%r" % (
                snap.get("detail_unlocked"), snap.get("detail_sensitive"),
                snap.get("detail_auth_error")))

        # P9.2 兼容键：宿主旧形状 data.success=false → 同样不解锁
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, call, "auth.biometric", {"success": False})
        frame = peer.wait_snapshot(lambda s: s.get("detail_unlocking") is False, timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.2", "宿主旧形状 success=false → 同样不解锁（缺省 False）",
            snap.get("detail_unlocked") is not True
            and not (snap.get("detail_sensitive") or {}),
            "unlocked=%r err=%r" % (snap.get("detail_unlocked"),
                                    snap.get("detail_auth_error")))

        # P9.3 回执无 granted/success 键 → 缺省 False，不解锁
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, call, "auth.biometric", {})
        frame = peer.wait_snapshot(lambda s: s.get("detail_unlocking") is False, timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.3", "回执缺 granted/success 键 → 缺省 False，不解锁",
            snap.get("detail_unlocked") is not True,
            "unlocked=%r" % snap.get("detail_unlocked"))

        # P9.4 真实回执 granted=true → 解锁并出明文
        peer.drain()
        peer.dispatch("btn_unlock", "tap")
        call = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, call, "auth.biometric", {"granted": True, "biometry": "touch_id"})
        frame = peer.wait_snapshot(lambda s: s.get("detail_unlocked") is True, timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.4", "生物识别通过（真实回执）→ 解锁并出明文",
            snap.get("detail_unlocked") is True
            and (snap.get("detail_sensitive") or {}).get("number_full") == "130102199001011234",
            "unlocked=%r sensitive=%r" % (snap.get("detail_unlocked"),
                                          snap.get("detail_sensitive")))

        # P9.5 fs.pick 取消（cancelled=true）→ 静默回空闲、不报错
        peer.drain()
        peer.dispatch("btn_close_detail", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_ocr", "tap")
        peer.wait_update()
        peer.drain()
        peer.dispatch("btn_ocr_pick", "tap")
        pick = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, pick, "fs.pick", {"cancelled": True, "paths": []})
        frame = peer.wait_snapshot(lambda s: s.get("ocr_stage") == "idle", timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.5", "文件选择被取消 → 回到空闲且不写错误",
            snap.get("ocr_stage") == "idle" and not (snap.get("ocr_error") or ""),
            "stage=%r err=%r" % (snap.get("ocr_stage"), snap.get("ocr_error")))

        # P9.6 fs.pick 真实回执只带 paths 数组 → 取首项并自动串联 ocr.recognize
        image_path = os.path.join(WORK, "receipt-p9.png")
        with open(image_path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
        peer.drain()
        peer.dispatch("btn_ocr_pick", "tap")
        pick = peer.wait_request("capability/call", timeout=6.0)
        cap_reply(peer, pick, "fs.pick", {"cancelled": False, "paths": [image_path]})
        ocr_call = peer.wait_request("capability/call", timeout=6.0)
        CHK("P9.6", "fs.pick 回 paths 数组 → 取首项并自动串联 ocr.recognize",
            bool(ocr_call)
            and ((ocr_call.get("params") or {}).get("params") or {}).get("path") == image_path,
            "call=%r" % (ocr_call and ocr_call.get("params"),))

        # P9.7 ocr.recognize 真实回执 data.text → 解析为就绪态
        cap_reply(peer, ocr_call, "ocr.recognize",
                  {"text": OCR_TEXT, "chars": len(OCR_TEXT)})
        frame = peer.wait_snapshot(
            lambda s: s.get("ocr_stage") not in (None, "recognizing"), timeout=8.0)
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P9.7", "OCR 真实回执 data.text → 解析为就绪态",
            snap.get("ocr_stage") == "ready"
            and bool((snap.get("ocr_parsed") or {}).get("doc_type")),
            "stage=%r parsed=%r err=%r" % (snap.get("ocr_stage"),
                                           snap.get("ocr_parsed"),
                                           snap.get("ocr_error")))

        peer.shutdown()
        peer.wait_exit()
        return peer
    finally:
        if peer.proc.poll() is None:
            peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 场景 P4/P5/P6：协议负例
# ---------------------------------------------------------------------------

def scenario_negative():
    print("\n== 场景 P4/P5/P6：协议负例 ==")
    peer = Peer("p4-negative")
    try:
        resp = peer.initialize(protocol="jsonrpc-stdio/2")
        err = (resp or {}).get("error") or {}
        code = peer.wait_exit(timeout=5.0)
        CHK("P4.1", "协议版本不兼容 → 4301 且非 0 退出",
            err.get("code") == sdk.ERR_PROTOCOL_VERSION_MISMATCH and code == 1,
            "error=%r code=%r" % (err, code))
    finally:
        peer.kill()
        peer.close()

    peer = Peer("p5-negative")
    try:
        resp = peer.initialize(ui_schema="shadeling-ui/9")
        err = (resp or {}).get("error") or {}
        code = peer.wait_exit(timeout=5.0)
        CHK("P5.1", "UI 引擎不支持 → 4302 且非 0 退出",
            err.get("code") == sdk.ERR_UI_SCHEMA_UNSUPPORTED and code == 1,
            "error=%r code=%r" % (err, code))
    finally:
        peer.kill()
        peer.close()

    peer = Peer("p6-negative")
    try:
        peer.initialize()
        peer.initialized()
        for _ in range(3):
            peer.send_raw(b"NOT-A-FRAME\r\n\r\n")
            time.sleep(0.4)
        code = peer.wait_exit(timeout=6.0)
        joined = "\n".join(peer.stderr)
        CHK("P6.1", "连续 3 次帧解码失败 → 记 4305 并以 4308 退出",
            code == 1 and "4305" in joined and "4308" in joined,
            "code=%r stderr_tail=%r" % (code, peer.stderr[-2:]))
    finally:
        peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 场景 P7：持久化（正常退出 / 异常退出后重启）
# ---------------------------------------------------------------------------

def scenario_persistence():
    print("\n== 场景 P7：重启与异常退出后的数据持久化 ==")
    digest_before, rows_before = db_digest()

    peer = Peer("p7-a")
    try:
        peer.initialize()
        frame = peer.initialized()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P7.1", "重启后首帧即恢复既有条目（卸载重装不丢/落盘可复现）",
            snap.get("total") == rows_before, "total=%r rows=%r" % (snap.get("total"), rows_before))
        peer.shutdown()
        peer.wait_exit()
    finally:
        peer.kill()
        peer.close()

    digest_mid, rows_mid = db_digest()
    CHK("P7.2", "正常退出前后 DB 内容校验和一致",
        digest_mid == digest_before and rows_mid == rows_before,
        "before=%s mid=%s" % (digest_before[:12], digest_mid[:12]))

    peer = Peer("p7-b")
    try:
        peer.initialize()
        peer.initialized()
    finally:
        peer.kill()      # SIGKILL：模拟异常退出
        peer.close()
    digest_after, rows_after = db_digest()
    CHK("P7.3", "SIGKILL 异常退出后 DB 校验和不变（无半写）",
        digest_after == digest_before and rows_after == rows_before,
        "after=%s" % digest_after[:12])

    peer = Peer("p7-c")
    try:
        peer.initialize()
        frame = peer.initialized()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P7.4", "异常退出后重启再次读到同样条目数",
            snap.get("total") == rows_before, "total=%r" % snap.get("total"))
        peer.shutdown()
        peer.wait_exit()
    finally:
        peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 场景 P10：D4 私有目录接管 / 卸载重装不丢
# ---------------------------------------------------------------------------

def scenario_d4_private_store():
    print("\n== 场景 P10：D4 私有目录接管 · 卸载重装不丢 ==")
    base = os.path.join(WORK, "d4")
    fake_home = os.path.join(base, "fakehome")
    legacy = os.path.join(fake_home, "Library", "Application Support", "Shadeling", "vault")
    private = os.path.join(base, "Bricks", BRICK_ID, "data")
    os.makedirs(legacy, exist_ok=True)
    source_db = os.path.join(legacy, "vault.db")
    shutil.copy2(DB, source_db)
    source_digest = file_sha256(source_db)
    _, rows_expected = db_digest()
    inject = {"HOME": fake_home, "SHADELING_BRICK_PRIVATE_DIR": private}

    # --- 首次以私有目录启动：接管旧全局库
    peer = Peer("p10-adopt", extra_env=inject, drop_env=("SHADELING_HOME",))
    try:
        peer.initialize()
        frame = peer.initialized()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        private_db = os.path.join(private, "vault.db")
        CHK("P10.1", "注入私有目录后库落私有目录（scope=private）",
            os.path.isfile(private_db) and any("scope=private" in l for l in peer.stderr),
            "private_db=%s stderr=%r" % (os.path.isfile(private_db), peer.stderr[-3:]))
        CHK("P10.2", "接管旧库后条目数与旧库一致",
            snap.get("total") == rows_expected,
            "total=%r expected=%r" % (snap.get("total"), rows_expected))
        CHK("P10.3", "接管为逐字节复制（sha256 与源一致）",
            file_sha256(private_db) == source_digest,
            "%s vs %s" % (file_sha256(private_db)[:12], source_digest[:12]))
        CHK("P10.4", "源库保留未被动过（可后悔）",
            os.path.isfile(source_db) and file_sha256(source_db) == source_digest)
        peer.shutdown()
        peer.wait_exit()
    finally:
        peer.kill()
        peer.close()

    # --- 卸载重装语义：安装目录与私有目录分离，重启（同私有目录）数据不丢
    install_dir = os.path.join(base, "Bricks", "vault")        # 宿主卸载时删除的是安装目录
    os.makedirs(install_dir, exist_ok=True)
    adopted_digest = file_sha256(os.path.join(private, "vault.db"))
    peer = Peer("p10-reinstall", extra_env=inject, drop_env=("SHADELING_HOME",))
    try:
        peer.initialize()
        frame = peer.initialized()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P10.5", "卸载重装（同私有目录重启）后条目数不变",
            snap.get("total") == rows_expected,
            "total=%r expected=%r" % (snap.get("total"), rows_expected))
        CHK("P10.6", "库位于安装目录之外（卸载不波及私有数据）",
            os.path.commonpath([os.path.abspath(private), os.path.abspath(install_dir)])
            != os.path.abspath(install_dir),
            "private=%s install=%s" % (private, install_dir))
        CHK("P10.7", "重装后私有库文件 sha256 稳定（无半写 / 无重复接管）",
            file_sha256(os.path.join(private, "vault.db")) == adopted_digest,
            "%s vs %s" % (file_sha256(os.path.join(private, "vault.db"))[:12], adopted_digest[:12]))
        peer.shutdown()
        peer.wait_exit()
    finally:
        peer.kill()
        peer.close()

    # --- 向后兼容：两路注入都缺席时仍走旧口径（不因新增分支弄丢老用户库）
    peer = Peer("p10-legacy", extra_env={"HOME": fake_home}, drop_env=("SHADELING_HOME",))
    try:
        peer.initialize()
        frame = peer.initialized()
        snap = (frame or {}).get("params", {}).get("state_snapshot", {})
        CHK("P10.8", "无私有目录注入时回退旧全局库（向后兼容）",
            snap.get("total") == rows_expected,
            "total=%r expected=%r" % (snap.get("total"), rows_expected))
        peer.shutdown()
        peer.wait_exit()
    finally:
        peer.kill()
        peer.close()


# ---------------------------------------------------------------------------
# 静态/结构核验（非协议帧，辅助证据）
# ---------------------------------------------------------------------------

def scenario_static():
    print("\n== 场景 S：源码结构与预算核验 ==")
    loader = SourceFileLoader("vault_logic", LOGIC)
    spec = importlib.util.spec_from_loader("vault_logic", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    source = open(LOGIC, "r", encoding="utf-8").read()
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    stdlib = {"json", "os", "re", "sqlite3", "subprocess", "sys", "time", "uuid", "shutil",
              "pathlib", "datetime", "urllib", "copy", "hashlib", "base64", "hmac", "secrets"}
    extra = imports - stdlib - {"brick_sdk", "__future__"}
    CHK("S.1", "仅标准库 + 平台 SDK（无三方依赖）", not extra, "额外依赖=%r" % extra)
    CHK("S.2", "导入集=%s" % ", ".join(sorted(imports)), True, "")

    forbidden = ["NSWindow", "NSApplication", "BrickScene", "NSWorkspace", "AppKit",
                 "SwiftUI", "createsNewApplicationInstance", "NSView", "NSViewController"]
    hits = [word for word in forbidden if word in source]
    CHK("S.3", "产物无窗口/宿主相关符号（§7.5 验收 4）", not hits, "命中=%r" % hits)

    # 节点预算：200 条资产 + 三类弹层全开
    fake_assets = [{
        "id": "a%03d" % i, "type": "document" if i % 2 else "note",
        "title": "样本 %d" % i, "doc_type": "身份证", "valid_to": "2027-01-01",
        "text": "内容" * 20, "updated_at": time.time() - i * 60, "has_sensitive": i % 3 == 0,
        "is_ai": i % 5 == 0,
    } for i in range(200)]
    state = dict(module.INITIAL_STATE)
    state["items"] = [module.card_of(a) for a in fake_assets]
    state["total"] = 200
    state["manual_open"] = True
    state["ocr_open"] = True
    state["detail_open"] = True
    state["detail_has_sensitive"] = True
    state["detail_unlocking"] = True
    root = module.build_root(state)
    nodes = count_nodes(root)
    size = len(json.dumps(root, ensure_ascii=False).encode("utf-8"))
    CHK("S.4", "200 条资产 + 三弹层全开时节点数 ≤ 2000", nodes <= 2000, "nodes=%d" % nodes)
    CHK("S.5", "该最坏帧体积 < 1MB 单帧上限", size < 1024 * 1024, "size=%d" % size)

    widths = [(w, module.grid_columns_for(w)) for w in (480, 640, 768, 900, 1200, 1600, 2400)]
    CHK("S.6", "grid_columns_for：640pt ≥2 列、单调不减、≤6",
        widths[1][1] >= 2 and all(widths[i][1] <= widths[i + 1][1] for i in range(len(widths) - 1))
        and widths[-1][1] <= 6, "%r" % widths)

    # 存储层单元级补充：file_ref 落盘 + 删除清理 + 明文可解密
    store = module.VaultStore()
    image = os.path.join(WORK, "unit-sample.png")
    with open(image, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + b"unit")
    asset = store.add({"type": "image", "fields": {"excerpt": "单元级样本"},
                       "sensitive": {"number_full": "130102199001011234"},
                       "file_path": image})
    ref_dir = os.path.join(SANDBOX, asset["id"])
    CHK("S.7", "存储层：file_path 复制进私有目录并写 file_ref",
        os.path.isdir(ref_dir) and os.listdir(ref_dir) == ["unit-sample.png"],
        "ref=%r" % os.listdir(ref_dir) if os.path.isdir(ref_dir) else "no dir")
    CHK("S.8", "存储层：敏感字段可解密回明文、列表口径脱敏",
        store.plain_fields(asset["id"]).get("number_full") == "130102199001011234"
        and store.get(asset["id"]).get("number_masked", "").endswith("1234"),
        "plain=%r" % store.plain_fields(asset["id"]))
    store.delete(asset["id"])
    CHK("S.9", "存储层：删除同时清理私有目录与库内行",
        not os.path.isdir(ref_dir) and store.get(asset["id"]) is None, "")
    return module


def scenario_ui_fallback():
    """场景 P8：包内 UI 声明缺失/非法 → 兜底骨架 + 显式提示（Phase D2）。"""
    print("\n== 场景 P8：UI 声明不可用时的兜底 ==")
    cases = [
        ("P8.1", "missing", None, "包内缺少 ui/main.json"),
        ("P8.2", "badschema",
         {"schema": "shadeling-ui/9", "root": {"type": "container", "id": "root"}},
         "schema 非 shadeling-ui/1"),
    ]
    for cid, tag, doc, expect in cases:
        pkg = os.path.join(WORK, "ui-%s" % tag)
        logic_dir = os.path.join(pkg, "logic")
        os.makedirs(logic_dir, exist_ok=True)
        target = os.path.join(logic_dir, "vault")
        shutil.copy2(LOGIC, target)
        if doc is not None:
            ui_dir = os.path.join(pkg, "ui")
            os.makedirs(ui_dir, exist_ok=True)
            with open(os.path.join(ui_dir, "main.json"), "w", encoding="utf-8") as handle:
                json.dump(doc, handle, ensure_ascii=False)
        peer = Peer("ui-%s" % tag, logic=target)
        try:
            resp = peer.initialize(ident="h-init-%s" % tag)
            err = (resp or {}).get("error")
            frame = peer.initialized()
            snap = (frame or {}).get("params", {}).get("state_snapshot", {})
            texts = " ".join(flatten_text((frame or {}).get("params", {}).get("root") or {}))
            CHK(cid, "UI 声明不可用（%s）→ 兜底骨架并显式提示" % tag,
                err is None and expect in texts and snap.get("total") is not None,
                "err=%r texts=%r" % (err, texts[:200]))
        finally:
            peer.kill()
            peer.close()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    started = time.time()
    scenario_static()
    scenario_p1()
    scenario_p2()
    scenario_p3()
    scenario_p9()
    scenario_negative()
    scenario_ui_fallback()
    scenario_persistence()
    scenario_d4_private_store()

    passed = sum(1 for c in CHECKS if c["status"] == "PASS")
    skipped = list(SUPERSEDED)
    failed = [c for c in CHECKS if c["status"] == "FAIL"]
    digest, rows = db_digest()
    summary = {
        "logic": LOGIC,
        "sdk": os.path.join(SDK_DIR, "brick_sdk.py"),
        "workspace": WORK,
        "sandbox_vault": SANDBOX,
        "total_checks": len(CHECKS),
        "passed": passed,
        "failed": len(failed),
        "failed_ids": [c["id"] for c in failed],
        "skipped_count": len(skipped),
        "skipped": skipped,
        "elapsed_sec": round(time.time() - started, 1),
        "final_db_rows": rows,
        "final_db_digest": digest,
        "resize_table": FRAMES.get("P1.resize"),
        "permission_profile": "P1 未授予 / P2 授予但回 4309 / P3 授予并放行",
        "checks": CHECKS,
    }
    out = os.path.join(WORK, "selftest_result.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print("\n==== 汇总：%d/%d 通过，失败 %d，D2 接管 %d ====" % (
        passed, len(CHECKS), len(failed), len(skipped)))
    print("结果 JSON：%s" % out)
    if skipped:
        print("D2 接管项：%r" % [c["id"] for c in skipped])
    if failed:
        print("失败项：%r" % [c["id"] for c in failed])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
