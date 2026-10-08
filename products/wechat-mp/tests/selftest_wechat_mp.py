#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-mp logic 自测（P1~P7，能力驱动，不出网）。

用法：
    python3 products/wechat-mp/tests/selftest_wechat_mp.py

覆盖：
  P1 文档与状态面（ui/main.json 契约、state 键齐备、render 幂等、fallback 骨架）
  P2 主题与 Markdown→内联样式 HTML（对齐 Themes.swift pine / plainInk）
  P3 凭据与令牌私有目录 0600 存储 + 旧目录接管
  P4 页面 / 派生字段 / 元信息校验
  P5 受控网络写未授予时的**显式降级**（不静默、不置成功态、零出网）
  P6 授予 agent.web.write 后的全链路（token 缓存与 40001 重取、素材、草稿、发布探测/提交/查询）
  P7 白名单 / 10MB / 事件覆盖 与 未知事件处理
"""

import copy
import importlib.machinery
import importlib.util
import json
import os
import stat
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PRODUCT))
LOGIC_PATH = os.path.join(PRODUCT, "logic", "wechat_mp")

CANDIDATES = [
    os.environ.get("SHADELING_BRICK_SDK_DIR"),
    os.path.join(ROOT, "sdk", "python"),
    os.path.join(os.path.dirname(ROOT), "Shadeling", "sdk", "python"),
    os.path.expanduser("~/Dev/Shadeling/sdk/python"),
]
SDK_DIR = None
for cand in CANDIDATES:
    if cand and os.path.isfile(os.path.join(cand, "brick_sdk.py")):
        SDK_DIR = cand
        break
if SDK_DIR is None:
    sys.stderr.write("未找到 brick_sdk.py（可设置 SHADELING_BRICK_SDK_DIR）\n")
    raise SystemExit(2)
os.environ["SHADELING_BRICK_SDK_DIR"] = SDK_DIR

LOADER = importlib.machinery.SourceFileLoader("wechat_mp_logic", LOGIC_PATH)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
mod = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(mod)

TMP = tempfile.mkdtemp(prefix="wechat-mp-selftest-")
mod.APP.private_dir = TMP
mod.APP.granted_permissions = []
mod.APP.declared_permissions = ["network", "ui.clipboard.write", "fs.pick"]

AUDITS = []


def _collect_log(level, message):
    if "[audit]" in str(message):
        AUDITS.append(str(message))


mod.APP.log = _collect_log

PASSED = []
FAILED = []


def check(name, ok, detail=""):
    if ok:
        PASSED.append(name)
        print("  PASS  %s" % name)
    else:
        FAILED.append((name, detail))
        print("  FAIL  %s%s" % (name, (" —— %s" % detail) if detail else ""))
    return bool(ok)


def eq(name, actual, expected):
    return check(name, actual == expected, "期望 %r，实际 %r" % (expected, actual))


def contains(name, haystack, needle):
    return check(name, needle in (haystack or ""), "在 %r 中未找到 %r" % ((haystack or "")[:120], needle))


def fresh():
    state = copy.deepcopy(mod.STATE_SNAPSHOT)
    state["_rt"] = {}
    return state


def sync(state):
    mod._sync_derived(state)
    return state


def ev(node_id, event="tap", payload=None, ui_state=None):
    return {"node_id": node_id, "event": event, "payload": payload or {}, "ui_state": ui_state or {}}


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------

class FakeHost:
    def __init__(self):
        self.copied = []
        self.toasts = []
        self.picked = None

    def granted(self, permission):
        return True

    def copy_text(self, text, on_done=None):
        self.copied.append(text)
        if on_done:
            on_done(True, "复制成功")

    def pick_file(self, kinds, on_done):
        if self.picked:
            on_done(True, "已选择", self.picked)
        else:
            on_done(False, "未选择文件", None)

    def toast(self, text):
        self.toasts.append(text)


class FakeTransport:
    """模拟 api.weixin.qq.com（token 失效、48001 权限不足可切换）。"""

    def __init__(self):
        self.calls = []
        self.token_requests = 0
        self.deny_publish = False
        self.app_secret = "good"
        self._token = "tk-1"
        self._seq = 1

    @property
    def available(self):
        return "agent.web.write" in (mod.APP.granted_permissions or [])

    def why_unavailable(self):
        return ("写类网络能力 agent.web.write（G4，高危）未授予：测试连接 / 素材上传 / "
                "草稿增删刷新 / 发布探测与提交 暂不可用；该能力获批后无需改包即可恢复。")

    def invalidate(self):
        self._seq += 1
        self._token = "tk-%d" % self._seq

    def _ok(self, payload, on_done):
        on_done({"status": 200, "json": payload}, None)

    def _err(self, code, on_done):
        on_done({"status": 200, "json": {"errcode": code, "errmsg": "fake"}}, None)

    def request(self, req, on_done):
        self.calls.append(req)
        path = req["path"]
        query = req.get("query") or {}
        body = req.get("body") or {}
        if path == mod.PATHS["token"]:
            if query.get("secret") == self.app_secret + "-bad":
                self._err(40013, on_done)
                return
            self.token_requests += 1
            self._ok({"access_token": self._token, "expires_in": 7200}, on_done)
            return
        if query.get("access_token") != self._token:
            self._err(40001, on_done)
            return
        if path == mod.PATHS["material_add"]:
            self._ok({"media_id": "media-1", "url": "https://mmbiz.qpic.cn/fake.png"}, on_done)
        elif path == mod.PATHS["draft_add"]:
            self._ok({"media_id": "draft-new"}, on_done)
        elif path == mod.PATHS["draft_batchget"]:
            self._ok({"total_count": 1, "item_count": 1, "item": [{
                "media_id": "draft-1", "update_time": 1759881600,
                "content": {"news_item": [{"title": "旧稿", "digest": "摘要",
                                           "url": "https://mp.weixin.qq.com/s/fake"}]}}]}, on_done)
        elif path == mod.PATHS["draft_delete"]:
            self._ok({}, on_done)
        elif path == mod.PATHS["publish_batchget"]:
            if self.deny_publish:
                self._err(48001, on_done)
            else:
                self._ok({"total_count": 0, "item": []}, on_done)
        elif path == mod.PATHS["publish_submit"]:
            self._ok({"publish_id": "pub-1"}, on_done)
        elif path == mod.PATHS["publish_get"]:
            self._ok({"publish_status": 0, "article_id": "art-1"}, on_done)
        else:
            self._err(-1, on_done)


def grant_web_write():
    mod.APP.granted_permissions = ["ui.clipboard.write", "fs.pick", "agent.web.write"]


def revoke_all():
    mod.APP.granted_permissions = []


def new_env():
    transport = FakeTransport()
    host = FakeHost()
    mod.TRANSPORT = transport
    mod.HOST = host
    return transport, host


# ---------------------------------------------------------------------------
# P1 文档与状态面
# ---------------------------------------------------------------------------

def p1():
    print("\nP1 文档与状态面")
    check("P1.1 ui/main.json 载入为 shadeling-ui/1", mod.UI_DOC is not None
          and mod.UI_DOC.get("schema") == "shadeling-ui/1",
          "UI_LOAD_NOTE=%s" % mod.UI_LOAD_NOTE)
    check("P1.2 UI base root 合法", isinstance(mod.UI_BASE, dict) and mod.UI_BASE.get("id") == "root")
    check("P1.3 state_snapshot 键数 >= 53", len(mod.STATE_SNAPSHOT) >= 53,
          "实际 %d" % len(mod.STATE_SNAPSHOT))
    missing = [k for k in mod.STATE_SNAPSHOT if k not in mod.INITIAL_STATE]
    eq("P1.4 INITIAL_STATE 覆盖全部文档 state 键", missing, [])
    state = fresh()
    root = mod.build_root(state)
    check("P1.5 build_root 返回 root 节点", isinstance(root, dict) and root.get("type") == "container")
    check("P1.6 build_root 为深拷贝（不污染 UI_BASE）", root is not mod.UI_BASE
          and json.dumps(root, ensure_ascii=False) == json.dumps(mod.UI_BASE, ensure_ascii=False))
    root["props"]["padding"] = 999
    check("P1.7 修改返回节点不影响 UI_BASE", mod.UI_BASE["props"]["padding"] != 999)
    eq("P1.8 默认页与 is_account 一致", (state["page"], state["is_account"]), ("账号", True))
    again = mod.build_root(state)
    check("P1.9 render 幂等（两次 root 全等）",
          json.dumps(again, ensure_ascii=False) == json.dumps(mod.build_root(state), ensure_ascii=False))
    saved = mod.UI_BASE
    mod.UI_BASE = None
    mod.UI_LOAD_NOTE = "测试注入"
    fb = mod.build_root(fresh())
    mod.UI_BASE = saved
    check("P1.10 UI 声明缺失时给出显式 fallback", any(
        c.get("id") == "load_error" for c in fb.get("children", [])), json.dumps(fb)[:120])
    eq("P1.11 五页映射齐全", sorted(mod.PAGE_KEYS.keys()), ["发布", "素材", "编辑", "草稿", "账号"])


# ---------------------------------------------------------------------------
# P2 主题与渲染
# ---------------------------------------------------------------------------

def p2():
    print("\nP2 主题与 Markdown 渲染")
    pine = mod.theme_of("松绿")
    ink = mod.theme_of("素墨")
    eq("P2.1 松绿 accent 对齐 Themes.swift", pine["accent"], "#0f7b6c")
    eq("P2.2 素墨标题样式为下划线", ink["heading"], "underline")
    check("P2.3 两主题强调色不同", pine["accent"] != ink["accent"])
    eq("P2.4 空正文渲染为空串", mod.render_markdown("", "松绿"), "")
    h2 = mod.render_markdown("## 小标题", "松绿")
    contains("P2.5 松绿 h2 带左侧竖线", h2, "border-left:4px solid #0f7b6c")
    h2i = mod.render_markdown("## 小标题", "素墨")
    contains("P2.6 素墨 h2 带下划线", h2i, "border-bottom:1px solid #e0e0e0")
    rich = mod.render_markdown(
        "# 标题\n\n**粗体**与*斜体*与~~删除~~与`code`。\n\n> 引用一行\n\n- 甲\n- 乙\n\n1. 一\n2. 二\n\n---\n\n"
        "[链接](https://example.com) 与 ![图](https://x/y.png)\n\n```py\nprint(1)\n```", "松绿")
    contains("P2.7 粗体", rich, "<strong>粗体</strong>")
    contains("P2.8 斜体", rich, "<em>斜体</em>")
    contains("P2.9 删除线", rich, "<del>删除</del>")
    contains("P2.10 行内代码内联样式", rich, "<code style=\"padding:1px 5px;background:#f5f6f7")
    contains("P2.11 引用块", rich, "<blockquote style=\"margin:0 0 18px;padding:12px 16px;border-left:3px solid #0f7b6c")
    contains("P2.12 无序列表", rich, "<ul style=")
    contains("P2.13 有序列表", rich, "<ol style=")
    contains("P2.14 分割线", rich, "<hr style=\"border:none;border-top:1px solid #e6e6e6")
    contains("P2.15 链接", rich, "<a href=\"https://example.com\"")
    contains("P2.16 图片", rich, "<img src=\"https://x/y.png\"")
    contains("P2.17 代码块可换行", rich, "white-space:pre-wrap")
    contains("P2.18 正文包裹 section 内联字体", rich, "<section style=\"font-family:-apple-system")
    plain = mod.render_markdown("普通一段", "松绿")
    contains("P2.19 段落内联外边距", plain, "margin:0 0 18px")
    check("P2.20 不同主题产出不同 HTML",
          mod.render_markdown("## 标题", "松绿") != mod.render_markdown("## 标题", "素墨"))


# ---------------------------------------------------------------------------
# P3 凭据与令牌
# ---------------------------------------------------------------------------

def p3():
    print("\nP3 凭据 / 令牌私有目录 0600")
    store = mod._store()
    state = fresh()
    state["app_id"] = "wx123456"
    state["secret"] = "s3cret"
    mod.act_save_credentials(state, ev("btn_save_credentials"))
    path = store.account_path
    check("P3.1 凭据写入私有目录", os.path.isfile(path) and path.startswith(TMP), path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    eq("P3.2 凭据文件权限 0600", oct(mode), oct(0o600))
    loaded = store.load_account()
    eq("P3.3 凭据可读回", (loaded["app_id"], loaded["secret"]), ("wx123456", "s3cret"))
    eq("P3.4 保存后 store_path 同步", state["store_path"], path)
    store.save_token("tk-x", time.time() + 3600, "wx123456")
    eq("P3.5 令牌文件权限 0600", oct(stat.S_IMODE(os.stat(store.token_path).st_mode)), oct(0o600))
    bad = fresh()
    mod.act_save_credentials(bad, ev("btn_save_credentials", payload={"app_id": "wx", "app_secret": ""}))
    check("P3.6 缺字段保存失败且提示错误", bad["notice_is_error"], bad["notice_text"])
    legacy = os.path.join(TMP, "legacy")
    os.makedirs(legacy, exist_ok=True)
    with open(os.path.join(legacy, "account.json"), "w", encoding="utf-8") as fh:
        json.dump({"app_id": "wx-legacy", "secret": "ls"}, fh)
    old = mod.LEGACY_DIR
    try:
        mod.LEGACY_DIR = legacy
        adopted = mod.Store(os.path.join(TMP, "fresh-private"))
        data = adopted.load_account()
        check("P3.7 旧目录凭据可接管", data["app_id"] == "wx-legacy" and adopted.adopted_from_legacy)
    finally:
        mod.LEGACY_DIR = old


# ---------------------------------------------------------------------------
# P4 页面 / 派生
# ---------------------------------------------------------------------------

def p4():
    print("\nP4 页面切换与派生字段")
    state = fresh()
    for page, key in mod.PAGE_KEYS.items():
        mod.act_page_change(state, ev("nav_form", "change", ui_state={"page": page}))
        sync(state)
        others = [k for k, v in mod.PAGE_KEYS.items() if v != key and state[v]]
        check("P4.1 「%s」页互斥生效" % page, state[key] and not others, "异常互斥：%s" % others)
    eq("P4.2 page_label 跟随 page", state["page_label"], "发布")
    state = fresh()
    sync(state)
    check("P4.3 空凭据 → account_incomplete", state["account_incomplete"] and not state["account_complete"])
    state["app_id"], state["secret"] = "wx1", "sec"
    sync(state)
    check("P4.4 填齐凭据 → account_complete", state["account_complete"] and not state["account_incomplete"])
    check("P4.5 缺元信息提示三项", state["meta_hint_present"]
          and all(w in state["meta_hint"] for w in ("标题", "封面", "正文")), state["meta_hint"])
    state["payload_title"] = "标题"
    state["cover_media_id"] = "media-1"
    state["markdown_source"] = "# 正文"
    sync(state)
    check("P4.6 补齐后元信息提示消失", not state["meta_hint_present"], state["meta_hint"])
    eq("P4.7 封面值显示 media_id", state["cover_value"], "media-1")
    check("P4.8 HTML 渲染写入 _rt", state["_rt"]["html"].startswith("<section style="))
    contains("P4.9 预览给出行数说明", state["preview_lines"], "共 ")
    state["theme"] = "素墨"
    sync(state)
    contains("P4.10 theme_summary 随主题变化", state["theme_summary"], "黑白极简")
    state["assets"] = [{"media_id": "m1", "file_name": "a.png"}]
    state["drafts"] = [{"media_id": "d1", "title": "t"}]
    sync(state)
    eq("P4.11 计数派生", (state["assets_count"], state["drafts_count"]), (1, 1))


# ---------------------------------------------------------------------------
# P5 未授予 agent.web.write 时的显式降级
# ---------------------------------------------------------------------------

def p5():
    print("\nP5 受控网络写未授予 → 显式降级（零出网）")
    transport, host = new_env()
    revoke_all()
    state = fresh()
    state["app_id"], state["secret"] = "wx1", "sec"
    state["payload_title"] = "标题"
    state["markdown_source"] = "# 正文"
    state["cover_media_id"] = "media-1"
    sync(state)
    check("P5.1 upload_blocked 横幅置位", state["upload_blocked"] is True)
    mod.act_upload_asset(state, ev("btn_upload_asset"))
    check("P5.2 上传给出显式降级文案", state["notice_is_error"]
          and "G4" in state["notice_text"], state["notice_text"])
    eq("P5.3 未产生素材记录", state["assets"], [])
    mod.act_refresh_drafts(state, ev("btn_refresh_drafts"))
    check("P5.4 刷新草稿显式降级", state["notice_is_error"] and "未执行" in state["notice_text"])
    eq("P5.5 草稿列表保持空", state["drafts"], [])
    mod.act_save_draft(state, ev("btn_save_draft"))
    check("P5.6 保存草稿显式降级", state["notice_is_error"] and "未执行" in state["notice_text"])
    mod.act_test_connection(state, ev("btn_test_connection"))
    sync(state)
    check("P5.7 检测报告第 3 步标记未执行", "接口连通" in state["account_report"]
          and "未执行" in state["account_report"], state["account_report"][-80:])
    check("P5.8 发布权限保持 unknown + 原因", state["publish_unknown"]
          and "G4" in state["publish_reason"], state["publish_reason"])
    mod.act_refresh_publish_permission(state, ev("btn_reprobe_permission"))
    check("P5.9 探测权限显式降级", state["notice_is_error"] and state["publish_unknown"])
    mod.act_submit_publish(state, ev("btn_submit_publish"))
    check("P5.10 提交发布被拦截", state["notice_is_error"], state["notice_text"])
    mod.act_query_publish_status(state, ev("btn_query_publish", payload={"publish_id": "pub-x"}))
    check("P5.11 查询状态被拦截", state["notice_is_error"])
    eq("P5.12 全程零出网", transport.calls, [])
    check("P5.13 降级文案含恢复说明", "获批后" in transport.why_unavailable())

    real = mod.CapabilityTransport()
    done = []
    grant_web_write()
    real.request({"host": "evil.example.com", "method": "POST", "path": "/x"},
                 lambda res, err: done.append(err))
    check("P5.14 非白名单主机被拒", done and done[-1] and done[-1].kind == "protocol"
          and "白名单" in done[-1].message)
    done.clear()
    real.request({"host": mod.HOST_WHITELIST, "method": "POST", "path": "/x",
                  "multipart": {"size": mod.MULTIPART_LIMIT_BYTES + 1}},
                 lambda res, err: done.append(err))
    check("P5.15 超 10MB multipart 被拒", done and done[-1]
          and "10MB" in done[-1].message, str(done[-1].message if done and done[-1] else done))
    done.clear()
    revoke_all()
    real.request({"host": mod.HOST_WHITELIST, "method": "POST", "path": "/x"},
                 lambda res, err: done.append(err))
    check("P5.16 能力未授予返回 unavailable(4309)", done and done[-1]
          and done[-1].kind == "unavailable" and done[-1].code == 4309)
    done.clear()
    real.request({"host": mod.HOST_WHITELIST, "method": "POST", "path": "/x",
                  "multipart": {"size": mod.MULTIPART_LIMIT_BYTES + 1}},
                 lambda res, err: done.append(err))
    check("P5.17 未授予优先于白名单/体积校验", done and done[-1]
          and done[-1].kind == "unavailable")


# ---------------------------------------------------------------------------
# P6 授予 agent.web.write 后的全链路
# ---------------------------------------------------------------------------

def p6():
    print("\nP6 授予写类网络能力 → 全链路")
    transport, host = new_env()
    grant_web_write()
    state = fresh()
    state["app_id"], state["secret"] = "wx1", "sec"
    sync(state)
    check("P6.1 upload_blocked 随能力授予解除", state["upload_blocked"] is False)
    mod.act_test_connection(state, ev("btn_test_connection"))
    sync(state)
    check("P6.2 token 获取成功（1 次）", transport.token_requests == 1,
          "token_requests=%d" % transport.token_requests)
    check("P6.3 三步检测全绿", state["account_report"].count("✓") == 3, state["account_report"])
    check("P6.4 freepublish 探测通过 → granted", state["publish_granted"]
          and "可用" in state["publish_reason"])
    mod.act_test_connection(state, ev("btn_test_connection"))
    sync(state)
    eq("P6.5 测试连接强制刷新 token（对齐 v1 forceRefresh 语义）", transport.token_requests, 2)
    mod.act_refresh_drafts(state, ev("btn_refresh_drafts"))
    sync(state)
    eq("P6.6 普通接口命中 token 缓存（不重复请求）", transport.token_requests, 2)
    transport.invalidate()
    mod.act_refresh_drafts(state, ev("btn_refresh_drafts"))
    sync(state)
    eq("P6.6b 40001 自动刷新后重试成功", transport.token_requests, 3)
    eq("P6.7 草稿列表刷新 1 条", (state["drafts_count"], state["drafts"][0]["title"]), (1, "旧稿"))
    check("P6.8 草稿行含格式化时间", bool(state["drafts"][0]["updated_at"]))
    img = os.path.join(TMP, "cover.png")
    with open(img, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    host.picked = img
    mod.act_upload_asset(state, ev("btn_upload_asset"))
    sync(state)
    eq("P6.9 上传后素材计数 1", state["assets_count"], 1)
    eq("P6.10 素材记录 media_id", state["assets"][0]["media_id"], "media-1")
    mod.act_use_asset_as_cover(state, ev("media_row", "action", payload={"action": "use_asset_as_cover",
                                                                        "index": 0}))
    sync(state)
    eq("P6.11 设为封面生效", state["cover_value"], "media-1")
    mod.act_copy_asset_media_id(state, ev("media_row", "action",
                                          payload={"action": "copy_asset_media_id",
                                                   "item": state["assets"][0]}))
    check("P6.12 复制 media_id 入剪贴板", host.copied and host.copied[-1] == "media-1")
    state["payload_title"] = "新稿"
    state["markdown_source"] = "# 新稿\n\n内容"
    sync(state)
    mod.act_save_draft(state, ev("btn_save_draft"))
    sync(state)
    check("P6.13 保存草稿调用 draft/add", any(c["path"] == mod.PATHS["draft_add"] for c in transport.calls))
    check("P6.14 保存后自动刷新草稿", any(c["path"] == mod.PATHS["draft_batchget"] for c in transport.calls))
    no_cover = fresh()
    no_cover.update({"app_id": "wx1", "secret": "sec", "payload_title": "x",
                     "markdown_source": "# x"})
    sync(no_cover)
    before = len(transport.calls)
    mod.act_save_draft(no_cover, ev("btn_save_draft"))
    check("P6.15 缺封面不放行且不发请求", no_cover["notice_is_error"] and len(transport.calls) == before
          and "封面" in no_cover["notice_text"], no_cover["notice_text"])
    transport.deny_publish = True
    mod.act_refresh_publish_permission(state, ev("btn_reprobe_permission"))
    sync(state)
    check("P6.16 48001 → 隐藏发布入口并给原因", state["publish_denied"]
          and "48001" in state["publish_reason"], state["publish_reason"])
    eq("P6.17 未授权时发布目标归零", state["publish_target"], "未选择")
    transport.deny_publish = False
    mod.act_refresh_publish_permission(state, ev("btn_reprobe_permission"))
    sync(state)
    check("P6.18 复测恢复 granted", state["publish_granted"])
    mod.act_use_draft_as_target(state, ev("drafts_row", "action",
                                          payload={"action": "use_draft_as_target",
                                                   "item": state["drafts"][0]}))
    sync(state)
    contains("P6.19 设为发布目标写入标题", state["publish_target"], "旧稿")
    mod.act_delete_draft(state, ev("drafts_row", "action", payload={"action": "delete_draft",
                                                                    "item": state["drafts"][0]}))
    sync(state)
    check("P6.20 删除需二次确认", state["confirm_delete"]
          and state["delete_target_title"] == "旧稿")
    mod.act_cancel_delete_draft(state, ev("dialog_confirm_delete", "cancel"))
    sync(state)
    check("P6.21 取消后草稿保留", not state["confirm_delete"] and state["drafts_count"] == 1)
    mod.act_delete_draft(state, ev("drafts_row", "action", payload={"action": "delete_draft",
                                                                    "item": state["drafts"][0]}))
    mod.act_confirm_delete_draft(state, ev("dialog_confirm_delete", "confirm"))
    sync(state)
    eq("P6.22 确认后草稿移除", state["drafts_count"], 0)
    check("P6.23 删除调用 draft/delete", any(c["path"] == mod.PATHS["draft_delete"] for c in transport.calls))
    state["drafts"] = [{"media_id": "draft-1", "title": "旧稿"}]
    mod.act_select_draft(state, ev("drafts_list", "select", payload={"item": state["drafts"][0]}))
    mod.act_submit_publish(state, ev("btn_submit_publish"))
    sync(state)
    eq("P6.24 提交发布返回 publish_id", state["publish_id"], "pub-1")
    eq("P6.25 提交调用 freepublish/submit",
       [c["path"] for c in transport.calls].count(mod.PATHS["publish_submit"]), 1)
    mod.act_query_publish_status(state, ev("btn_query_publish", payload={"publish_id": "pub-1"}))
    sync(state)
    contains("P6.26 查询状态翻译为中文", state["publish_status"], "已成功")
    mod.act_copy_publish_status(state, ev("btn_copy_publish_status"))
    check("P6.27 复制发布状态", host.copied and "publish_status=0" in host.copied[-1])
    big = os.path.join(TMP, "big.png")
    with open(big, "wb") as fh:
        fh.truncate(mod.MULTIPART_LIMIT_BYTES + 1024)
    host.picked = big
    before = len(transport.calls)
    mod.act_upload_asset(state, ev("btn_upload_asset"))
    check("P6.28 本地超 10MB 拦截且不发请求", len(transport.calls) == before
          and "10MB" in state["notice_text"], state["notice_text"])
    host.picked = img
    mod.act_export_html(state, ev("btn_export_html"))
    export_path = state["_rt"].get("export_path")
    check("P6.29 导出 HTML 落私有目录", export_path and os.path.isfile(export_path)
          and export_path.startswith(TMP), str(export_path))
    mod.act_copy_html(state, ev("btn_copy_html"))
    check("P6.30 复制正文 HTML", host.copied and host.copied[-1] == state["_rt"]["html"])
    mod.act_copy_account_report(state, ev("btn_copy_report"))
    check("P6.31 复制检测报告", host.copied and "AppID" in host.copied[-1])
    mod.act_copy_store_path(state, ev("btn_copy_store_path"))
    check("P6.32 复制存储路径", host.copied and host.copied[-1].endswith("account.json"))
    mod.act_copy_notice(state, ev("btn_copy_notice"))
    check("P6.33 复制提示", host.copied and host.copied[-1] == state["notice_text"])
    mod.act_open_html(state, ev("btn_open_html"))
    check("P6.34 系统打开给出未开放说明", "未开放" in state["notice_text"])
    eq("P6.35 全部请求仅打到白名单主机",
       sorted({c["host"] for c in transport.calls}), [mod.HOST_WHITELIST])
    check("P6.36 写类请求均带 access_token",
          all((c.get("query") or {}).get("access_token") or c["path"] == mod.PATHS["token"]
              for c in transport.calls))
    check("P6.37 每次出网均留审计行（含主机与路径）", len(AUDITS) >= 8
          and all("api.weixin.qq.com" in line for line in AUDITS),
          "审计 %d 行：%s" % (len(AUDITS), AUDITS[:2]))


# ---------------------------------------------------------------------------
# P7 事件覆盖与未知事件
# ---------------------------------------------------------------------------

def p7():
    print("\nP7 事件覆盖与未知事件")
    actions = set()
    for name in mod.HANDLERS:
        actions.add(name)

    def walk(node):
        if not isinstance(node, dict):
            return
        for value in (node.get("on") or {}).values():
            if isinstance(value, str):
                declared.add(value)
        for action in ((node.get("props") or {}).get("actions") or []):
            if isinstance(action, dict) and action.get("action"):
                declared.add(action["action"])
        for child in node.get("children") or []:
            walk(child)

    declared = set()
    walk(mod.UI_DOC["root"])
    unknown = sorted(declared - actions)
    eq("P7.1 UI 文档声明的事件全部有实现", unknown, [])
    check("P7.2 声明事件数 >= 26（含卡片动作）", len(declared) >= 26, "实际 %d" % len(declared))
    transport, host = new_env()
    grant_web_write()
    state = fresh()
    mod._dispatch(state, {"node_id": "account_form", "event": "change",
                          "payload": {}, "ui_state": {"app_id": "wx1", "app_secret": "sec"}})
    eq("P7.3 change 事件并入表单值", (state["app_id"], state["secret"]), ("wx1", "sec"))
    mod._dispatch(state, {"node_id": "composer_source_form", "event": "change",
                          "payload": {"markdown": "# hi"}, "ui_state": {}})
    eq("P7.4 payload.markdown 映射 markdown_source", state["markdown_source"], "# hi")
    mod._dispatch(state, {"node_id": "theme_form", "event": "change",
                          "payload": {"values": {"theme": "素墨"}}, "ui_state": {}})
    eq("P7.5 嵌套 values 也可并入", state["theme"], "素墨")
    mod._dispatch(state, {"node_id": "btn_save_draft", "event": "tap", "payload": {}, "ui_state": {}})
    check("P7.6 节点 tap 派发到保存草稿", "草稿" in state["notice_text"] or state["notice_is_error"])
    mod._dispatch(state, {"node_id": "mystery_btn", "event": "tap", "payload": {}, "ui_state": {}})
    check("P7.7 未知事件显式报错不静默", state["notice_is_error"] and "未识别" in state["notice_text"])
    mod._dispatch(state, {"node_id": "publish_form", "event": "submit", "payload": {}, "ui_state": {}})
    check("P7.8 publish_form submit 派发查询状态", "publish" in state["notice_text"]
          or state["notice_is_error"])
    eq("P7.9 事件绑定注册数（tap+change+submit+select+overlay）", len(mod.APP._bindings),
       len(mod.NODE_ACTIONS) + len(mod.TAP_NODES))
    paths = sorted({c["path"] for c in transport.calls})
    check("P7.10 无越界路径", all(p.startswith("/cgi-bin/") for p in paths), str(paths))


def main():
    print("wechat-mp logic 自测（SDK=%s）" % SDK_DIR)
    print("logic=%s" % LOGIC_PATH)
    p1()
    p2()
    p3()
    p4()
    p5()
    p6()
    p7()
    total = len(PASSED) + len(FAILED)
    print("\n结果：%d/%d 通过" % (len(PASSED), total))
    if FAILED:
        print("失败项：")
        for name, detail in FAILED:
            print("  - %s %s" % (name, ("—— %s" % detail) if detail else ""))
        return 1
    print("全部通过：%d 项" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
