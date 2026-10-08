#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 文档离线校验器（Phase D2）——与 Swift ``UIDocumentValidator`` 共用一套规则表。

契约依据：``specs/Shadeling积木声明式UI架构设计与契约-v0.1.md`` §2.3（布局原语）/
§2.4（文档结构）/§4.1~§4.10（组件规格）/§7.5（Phase D 验收）。

规则表来源（逐条对齐，禁止擅自放宽）：
  - ``app/Sources/BrickRenderer/UIDocument.swift``：组件类型 / props 键白名单 / 事件面 / 图标白名单
  - ``app/Sources/BrickRenderer/UIDocumentValidator.swift``：id 文法 / 枚举值域 / 取值区间 / 叶子 children 规则
  - ``app/Sources/BrickRenderer/Interpolation.swift``：插值语法与格式化器白名单

用法::

    python3 scripts/verify_ui_doc.py products/vault/ui/main.json
    python3 scripts/verify_ui_doc.py --frame frame.json          # 校验单帧 root（同规则）
    cat frame.json | python3 scripts/verify_ui_doc.py --frame -

退出码：0 通过；1 有问题（逐条打印，fail-fast 与运行时一致时会给出首个问题）。
"""

import argparse
import json
import re
import sys

# --- 限额（对齐 BrickUIDocumentLimits.default 与校验器常量）---
MAX_NODES = 2000
MAX_DEPTH = 16
MAX_DOC_BYTES = 512 * 1024
MAX_CHILDREN_PER_CONTAINER = 64
MAX_LABEL = 200
MAX_LIST_ITEMS = 5000
MAX_FORM_FIELDS = 32
MAX_CARD_ACTIONS = 4
MAX_CARD_TAGS = 12

ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
CONDITION_PATTERN = re.compile(r"^!?[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
ACTION_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
ICON_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
TEMPLATE_PATTERN = re.compile(r"\{\{(.*?)\}\}", re.S)
TEMPLATE_BODY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(\s*\|\s*(date|bytes|percent|number))?$")

NODE_TYPES = (
    "container", "text", "button", "progress", "list", "card", "form", "overlay", "image", "icon", "grid",
)
CONTAINER_TYPES = ("container", "grid", "list")

PROPS = {
    "container": {"direction", "gap", "padding", "align", "background", "card_style"},
    "text": {"value", "style", "color", "lines", "truncate", "mono", "badge"},
    "button": {"label", "style", "icon", "busy", "disabled", "size"},
    "progress": {"style", "value", "label"},
    "list": {"items", "selection", "empty_state", "lazy"},
    "card": {"title", "subtitle", "meta", "tags", "badge", "icon", "thumbnail", "actions", "selectable"},
    "form": {"fields", "submit_label"},
    "overlay": {"kind", "visible", "title", "message", "content", "primary_action", "secondary_action",
                "confirm_label", "cancel_label", "danger", "text", "level", "auto_dismiss_ms",
                "duration_ms", "width"},
    "image": {"source", "fit", "height", "placeholder", "fallback_text"},
    "icon": {"name", "size", "color"},
    "grid": {"columns", "min_column_width", "gap"},
}

FORM_FIELD_KEYS = {"field_id", "kind", "label", "placeholder", "value", "options", "mode", "error",
                   "required", "disabled", "mono"}
# 仅 `textarea` 可用的字段键（对齐 UIDocument.swift `BrickFormFieldKeys.textareaOnly`，E1 前置 T4）
TEXTAREA_ONLY_FIELD_KEYS = ("mono",)
CARD_ACTION_KEYS = {"label", "action", "style"}

EVENTS = {
    "button": {"tap"},
    "list": {"select", "tap"},
    "card": {"tap", "select", "action"},
    "form": {"change", "submit"},
    "overlay": {"confirm", "cancel", "primary", "secondary"},
}

ENUMS = {
    "direction": ("vertical", "horizontal"),
    "align": ("start", "center", "end", "leading", "trailing"),
    "card_style": ("none", "card", "glass"),
    "text_style": ("title", "heading", "body", "caption", "label"),
    "button_style": ("primary", "secondary", "ghost", "danger"),
    "button_size": ("sm", "md", "lg"),
    "progress_style": ("linear", "circular", "spinner"),
    "list_selection": ("none", "single"),
    "form_kind": ("field", "textarea", "picker", "toggle", "checkbox", "secret"),
    "picker_mode": ("menu", "segment", "date"),
    "overlay_kind": ("sheet", "dialog", "banner", "toast"),
    "overlay_level": ("info", "success", "warning", "error"),
    "image_fit": ("fill", "fit"),
    "icon_size": ("sm", "md", "lg"),
}

ICON_WHITELIST = {
    "checkmark.circle", "checkmark.circle.fill", "circle", "circle.fill",
    "xmark.circle", "xmark.circle.fill",
    "exclamationmark.triangle", "exclamationmark.triangle.fill", "info.circle", "info.circle.fill",
    "questionmark.circle", "hourglass",
    "plus", "minus", "multiply", "checkmark", "xmark",
    "arrow.up", "arrow.down", "arrow.left", "arrow.right",
    "arrow.clockwise", "arrow.up.arrow.down",
    "trash", "pencil", "square.and.pencil", "doc", "doc.fill", "folder", "folder.fill",
    "magnifyingglass", "gearshape", "gearshape.fill", "ellipsis", "ellipsis.circle",
    "play.fill", "pause.fill", "stop.fill",
    "square.and.arrow.up", "square.and.arrow.down", "tray.and.arrow.up", "tray.and.arrow.down",
    "paperplane", "paperplane.fill", "bell", "bell.fill", "flag", "flag.fill",
    "star", "star.fill", "heart", "heart.fill", "bookmark", "bookmark.fill",
    "list.bullet", "square.grid.2x2", "chart.bar", "chart.pie", "tablecells",
    "externaldrive", "internaldrive", "externaldrive.badge.icloud",
    "person", "person.fill", "person.2", "person.2.fill", "person.crop.circle",
    # E1 前置 T3：随 Swift `BrickIconWhitelist` 同步补齐（wechat-mp 页签图标）
    "tray", "photo.on.rectangle.angled",
}


class Issues(object):
    def __init__(self):
        self.items = []

    def add(self, path, message):
        self.items.append("%s：%s" % (path, message))

    def __bool__(self):
        return bool(self.items)


def _templates(text):
    """返回字符串内的插值体列表。"""
    return [body.strip() for body in TEMPLATE_PATTERN.findall(text)]


def _check_templates(text, path, issues):
    for body in _templates(text):
        # 允许 `items: "{{state.rows}}"` 这类整体模板；body 语法 = 路径（可选格式化器）
        if not TEMPLATE_BODY_PATTERN.match(body):
            issues.add(path, "插值非法：`{{%s}}`（仅支持 路径 或 路径|date/bytes/percent/number）" % body)


def _check_string(value, path, issues, limit=MAX_LABEL):
    if not isinstance(value, str):
        issues.add(path, "必须是字符串")
        return False
    if len(value) > limit:
        issues.add(path, "长度超限：%d > %d" % (len(value), limit))
        return False
    _check_templates(value, path, issues)
    return True


def _check_enum(value, name, path, issues):
    if value is None:
        return
    if value not in ENUMS[name]:
        issues.add(path, "取值非法：`%s`（白名单：%s）" % (value, " / ".join(ENUMS[name])))


def _check_spacing(value, path, issues):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if isinstance(value, str):
            issues.add(path, "间距令牌 `%s`：需与 BrickTokenMap.spacingNames 对照（离线校验器不查令牌表）" % value)
            return
        issues.add(path, "必须是数字（0…64）或间距令牌名")
        return
    if not 0 <= value <= 64:
        issues.add(path, "超出范围 0…64：%s" % value)


def _check_icon(name, path, issues):
    if not isinstance(name, str) or not ICON_PATTERN.match(name):
        issues.add(path, "图标名非法：`%s`" % name)
        return
    if name not in ICON_WHITELIST:
        issues.add(path, "图标不在白名单：`%s`（契约 §4.10）" % name)


def check_node(node, path, issues, seen, depth=1):
    if depth > MAX_DEPTH:
        issues.add(path, "节点深度超限：%d > %d" % (depth, MAX_DEPTH))
        return
    if not isinstance(node, dict):
        issues.add(path, "节点必须是对象")
        return

    for key in node:
        if key in ("type", "id", "props", "children", "if", "on"):
            continue
        if key == "subtype":
            issues.add(path, "已废弃节点键 `subtype`：overlay 子类载体统一为 `props.kind`（§2.5-9），请删除顶层 subtype")
        else:
            issues.add(path, "未知节点键：`%s`" % key)

    type_name = node.get("type")
    if type_name not in NODE_TYPES:
        issues.add(path, "未知组件类型：`%s`（白名单：%s）" % (type_name, " / ".join(NODE_TYPES)))
        return

    node_id = node.get("id")
    if not isinstance(node_id, str) or not ID_PATTERN.match(node_id):
        issues.add(path, "节点 id 非法（字母开头、仅字母/数字/下划线/短横线、≤64）：`%s`" % node_id)
    elif node_id in seen:
        issues.add(path, "节点 id 重复：`%s`（已在 %s 出现）" % (node_id, seen[node_id]))
    else:
        seen[node_id] = path

    here = "%s/%s" % (path, node_id)
    props = node.get("props") or {}
    if not isinstance(props, dict):
        issues.add(here, "props 必须是对象")
        props = {}
    for key in sorted(props):
        if key not in PROPS[type_name]:
            issues.add(here, "`%s` 不支持 props 键 `%s`" % (type_name, key))

    children = node.get("children") or []
    if children and type_name not in CONTAINER_TYPES:
        issues.add(here, "`%s` 是叶子组件，不允许 children（%d 个）" % (type_name, len(children)))
    if type_name == "list" and len(children) > 1:
        issues.add(here, "`list` 最多一个子节点（行模板），实际 %d 个" % len(children))
    if len(children) > MAX_CHILDREN_PER_CONTAINER:
        issues.add(here, "单容器子节点数超限：%d > %d" % (len(children), MAX_CHILDREN_PER_CONTAINER))

    condition = node.get("if")
    if condition is not None:
        if not isinstance(condition, str) or not CONDITION_PATTERN.match(condition):
            issues.add(here, "if 条件非法（仅 `state.<路径>` / `!state.<路径>`）：`%s`" % condition)

    on = node.get("on")
    if on is not None:
        if not isinstance(on, dict):
            issues.add(here, "on 必须是对象")
        else:
            allowed = EVENTS.get(type_name)
            if allowed is None:
                issues.add(here, "`%s` 不支持事件绑定（on）" % type_name)
            else:
                for key in sorted(on):
                    if key not in allowed:
                        issues.add(here, "不支持的事件 `%s`（允许：%s）" % (key, " / ".join(sorted(allowed))))
                    action = on[key]
                    if not isinstance(action, str) or not ACTION_PATTERN.match(action):
                        issues.add(here, "on.%s 动作名非法：`%s`" % (key, action))

    _check_props(type_name, props, here, issues)
    _check_overlay_content(node, type_name, props, here, issues, seen, depth)

    for child in children:
        check_node(child, here, issues, seen, depth + 1)


def _check_overlay_content(node, type_name, props, path, issues, seen, depth):
    if type_name != "overlay":
        return
    content = props.get("content")
    if content is None:
        return
    if not isinstance(content, dict):
        issues.add(path, "overlay content 必须是单个合法节点对象")
        return
    check_node(content, "%s/content" % path, issues, seen, depth + 1)


def _check_props(type_name, props, path, issues):
    if type_name == "container":
        _check_enum(props.get("direction"), "direction", path + ".direction", issues)
        _check_enum(props.get("align"), "align", path + ".align", issues)
        _check_enum(props.get("card_style"), "card_style", path + ".card_style", issues)
        _check_spacing(props.get("gap"), path + ".gap", issues)
        _check_spacing(props.get("padding"), path + ".padding", issues)
        if props.get("background") is not None:
            issues.add(path + ".background", "颜色令牌 `%s`：需与 BrickTokenMap.colorNames 对照（离线校验器不查令牌表）"
                       % props.get("background"))

    elif type_name == "grid":
        columns, minimum = props.get("columns"), props.get("min_column_width")
        if columns is None and minimum is None:
            issues.add(path, "grid 需至少声明 `columns` 或 `min_column_width` 之一")
        if columns is not None:
            if isinstance(columns, bool) or not isinstance(columns, int):
                issues.add(path + ".columns", "必须是整数")
            elif not 1 <= columns <= 12:
                issues.add(path + ".columns", "超出范围 1…12：%s" % columns)
        if minimum is not None:
            if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
                issues.add(path + ".min_column_width", "必须是数字（pt）")
            elif not 60 <= minimum <= 640:
                issues.add(path + ".min_column_width", "超出范围 60…640：%s" % minimum)
        _check_spacing(props.get("gap"), path + ".gap", issues)

    elif type_name == "text":
        if props.get("value") is None:
            issues.add(path, "text 缺少 value")
        else:
            _check_string(props.get("value"), path + ".value", issues)
        _check_enum(props.get("style"), "text_style", path + ".style", issues)
        lines = props.get("lines")
        if lines is not None:
            if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 20:
                issues.add(path + ".lines", "必须是 1…20 的整数：%s" % lines)

    elif type_name == "button":
        if props.get("label") is None:
            issues.add(path, "button 缺少 label")
        else:
            _check_string(props.get("label"), path + ".label", issues)
        _check_enum(props.get("style"), "button_style", path + ".style", issues)
        _check_enum(props.get("size"), "button_size", path + ".size", issues)
        if props.get("icon") is not None:
            _check_icon(props.get("icon"), path + ".icon", issues)

    elif type_name == "progress":
        _check_enum(props.get("style"), "progress_style", path + ".style", issues)
        if props.get("label") is not None:
            _check_string(props.get("label"), path + ".label", issues)

    elif type_name == "list":
        items = props.get("items")
        if items is not None:
            if isinstance(items, list):
                if len(items) > MAX_LIST_ITEMS:
                    issues.add(path + ".items", "行数超限：%d > %d" % (len(items), MAX_LIST_ITEMS))
            elif isinstance(items, str):
                _check_templates(items, path + ".items", issues)
            else:
                issues.add(path + ".items", "必须是数组或插值模板字符串")
        _check_enum(props.get("selection"), "list_selection", path + ".selection", issues)
        if props.get("empty_state") is not None:
            _check_string(props.get("empty_state"), path + ".empty_state", issues)

    elif type_name == "card":
        for key in ("title", "subtitle", "meta", "badge"):
            if props.get(key) is not None:
                _check_string(props.get(key), "%s.%s" % (path, key), issues)
        tags = props.get("tags")
        if tags is not None:
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                issues.add(path + ".tags", "必须是字符串数组")
            elif len(tags) > MAX_CARD_TAGS:
                issues.add(path + ".tags", "数量超限：%d > %d" % (len(tags), MAX_CARD_TAGS))
        if props.get("icon") is not None:
            _check_icon(props.get("icon"), path + ".icon", issues)
        actions = props.get("actions")
        if actions is not None:
            if not isinstance(actions, list):
                issues.add(path + ".actions", "必须是数组")
            else:
                if len(actions) > MAX_CARD_ACTIONS:
                    issues.add(path + ".actions", "数量超限：%d > %d" % (len(actions), MAX_CARD_ACTIONS))
                for index, action in enumerate(actions):
                    spot = "%s.actions[%d]" % (path, index)
                    if not isinstance(action, dict):
                        issues.add(spot, "必须是对象")
                        continue
                    for key in action:
                        if key not in CARD_ACTION_KEYS:
                            issues.add(spot, "不支持键 `%s`" % key)
                    if not isinstance(action.get("label"), str) or not action.get("label"):
                        issues.add(spot, "缺少 label")
                    name = action.get("action")
                    if not isinstance(name, str) or not ACTION_PATTERN.match(name):
                        issues.add(spot, "action 名非法：`%s`" % name)
                    if action.get("style") is not None:
                        _check_enum(action.get("style"), "button_style", spot + ".style", issues)

    elif type_name == "form":
        fields = props.get("fields")
        if not isinstance(fields, list):
            issues.add(path, "form 缺少 fields 数组")
        else:
            if len(fields) > MAX_FORM_FIELDS:
                issues.add(path + ".fields", "数量超限：%d > %d" % (len(fields), MAX_FORM_FIELDS))
            seen_ids = set()
            for index, field in enumerate(fields):
                spot = "%s.fields[%d]" % (path, index)
                if not isinstance(field, dict):
                    issues.add(spot, "必须是对象")
                    continue
                for key in field:
                    if key not in FORM_FIELD_KEYS:
                        issues.add(spot, "不支持键 `%s`" % key)
                field_id = field.get("field_id")
                if not isinstance(field_id, str) or not ID_PATTERN.match(field_id):
                    issues.add(spot, "field_id 非法：`%s`" % field_id)
                elif field_id in seen_ids:
                    issues.add(spot, "field_id 重复：`%s`" % field_id)
                else:
                    seen_ids.add(field_id)
                kind = field.get("kind")
                if kind not in ENUMS["form_kind"]:
                    issues.add(spot, "kind 非法（白名单：%s）：`%s`" % (" / ".join(ENUMS["form_kind"]), kind))
                for key in TEXTAREA_ONLY_FIELD_KEYS:
                    if key in field:
                        if kind != "textarea":
                            issues.add(spot, "键 `%s` 仅 textarea 可用（当前 kind=%s）" % (key, kind))
                        elif not isinstance(field.get(key), bool):
                            issues.add(spot, "键 `%s` 必须为 bool" % key)
                if field.get("label") is not None:
                    _check_string(field.get("label"), spot + ".label", issues)
                if field.get("value") is not None:
                    _check_string(field.get("value"), spot + ".value", issues)
                if field.get("error") is not None:
                    _check_string(field.get("error"), spot + ".error", issues)
                options = field.get("options")
                if options is not None:
                    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
                        issues.add(spot, "options 必须是字符串数组")
                    elif len(options) > 64:
                        issues.add(spot, "options 数量超限：%d > 64" % len(options))
                if field.get("mode") is not None:
                    _check_enum(field.get("mode"), "picker_mode", spot + ".mode", issues)
        if props.get("submit_label") is not None:
            _check_string(props.get("submit_label"), path + ".submit_label", issues)

    elif type_name == "overlay":
        kind = props.get("kind")
        _check_enum(kind, "overlay_kind", path + ".kind", issues)
        effective = kind if kind in ENUMS["overlay_kind"] else "banner"
        for key in ("title", "message", "text", "confirm_label", "cancel_label", "primary_action",
                    "secondary_action"):
            if props.get(key) is not None:
                _check_string(props.get(key), "%s.%s" % (path, key), issues)
        _check_enum(props.get("level"), "overlay_level", path + ".level", issues)
        if props.get("danger") is not None and not isinstance(props.get("danger"), bool):
            issues.add(path + ".danger", "必须是布尔值")
        if props.get("visible") is not None:
            value = props.get("visible")
            if not isinstance(value, str) or not TEMPLATE_PATTERN.search(value):
                issues.add(path + ".visible", "必须是插值字符串（如 `{{state.manual_open}}`）：`%s`" % value)
            else:
                _check_templates(value, path + ".visible", issues)
        for key in ("auto_dismiss_ms", "duration_ms", "width"):
            number = props.get(key)
            if number is not None:
                if isinstance(number, bool) or not isinstance(number, (int, float)) or number < 0:
                    issues.add("%s.%s" % (path, key), "必须是非负数字")
        if effective in ("banner", "toast") and not isinstance(props.get("text"), str):
            issues.add(path, "overlay kind=%s 缺少 text" % effective)

    elif type_name == "image":
        source = props.get("source")
        if not isinstance(source, str) or not source:
            issues.add(path, "image 缺少字符串 source（包内相对路径）")
        else:
            _check_templates(source, path + ".source", issues)
            if source.startswith("/") and not source.startswith("{{"):
                issues.add(path + ".source", "不允许绝对路径：`%s`" % source)
            if ".." in source:
                issues.add(path + ".source", "不允许 `..` 上跳：`%s`" % source)
            if "://" in source:
                issues.add(path + ".source", "不允许远程 URL：`%s`" % source)
        _check_enum(props.get("fit"), "image_fit", path + ".fit", issues)

    elif type_name == "icon":
        name = props.get("name")
        if name is None:
            issues.add(path, "icon 缺少 name")
        else:
            _check_icon(name, path + ".name", issues)
        _check_enum(props.get("size"), "icon_size", path + ".size", issues)


def _count_nodes(root):
    count, pending, depth_max = 0, [(root, 1)], 0
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, dict):
            continue
        count += 1
        depth_max = max(depth_max, depth)
        for child in node.get("children") or []:
            pending.append((child, depth + 1))
        content = (node.get("props") or {}).get("content")
        if isinstance(content, dict):
            pending.append((content, depth + 1))
    return count, depth_max


def _collect_template_paths(root, found):
    """收集所有插值路径（含 overlay content 子树），用于与 state_snapshot 对照。"""
    def scan(value):
        if isinstance(value, str):
            for body in _templates(value):
                path = body.split("|")[0].strip()
                found.add(path)
        elif isinstance(value, dict):
            for item in value.values():
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)

    pending = [root]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            continue
        scan(node.get("props") or {})
        if node.get("if"):
            found.add(str(node["if"]).lstrip("!"))
        for child in node.get("children") or []:
            pending.append(child)
        content = (node.get("props") or {}).get("content")
        if isinstance(content, dict):
            pending.append(content)


def verify_document(document, issues, check_state_paths=True):
    if document.get("schema") != "shadeling-ui/1":
        issues.add("$", "schema 必须是 `shadeling-ui/1`：`%s`" % document.get("schema"))
    root = document.get("root")
    if not isinstance(root, dict):
        issues.add("$", "缺少 root 节点对象")
        return
    seen = {}
    check_node(root, "$", issues, seen)
    payload = json.dumps(root, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_DOC_BYTES:
        issues.add("$", "UI 文档体积超限：%d > %d 字节" % (len(payload), MAX_DOC_BYTES))
    count, depth = _count_nodes(root)
    if count > MAX_NODES:
        issues.add("$", "节点数超限：%d > %d" % (count, MAX_NODES))
    if depth > MAX_DEPTH:
        issues.add("$", "节点深度超限：%d > %d" % (depth, MAX_DEPTH))

    if check_state_paths:
        snapshot = document.get("state_snapshot") or {}
        found = set()
        _collect_template_paths(root, found)
        for path in sorted(found):
            segments = path.split(".")
            if not segments:
                continue
            head = segments[0]
            if head in ("item", "index"):
                continue
            if head != "state":
                issues.add("$.state_snapshot", "插值未以 `state.` 开头：`%s`" % path)
                continue
            if len(segments) < 2:
                issues.add("$.state_snapshot", "插值缺少字段名：`%s`" % path)
                continue
            key = segments[1]
            if key in ("item", "index"):
                continue  # list 行模板作用域：渲染器逐行注入 state.item / state.index
            if key not in snapshot:
                issues.add("$.state_snapshot", "插值引用了快照中不存在的字段：`%s`" % path)
    return count, depth


def verify_frame(root, issues):
    seen = {}
    check_node(root, "$", issues, seen)
    count, depth = _count_nodes(root)
    if count > MAX_NODES:
        issues.add("$", "节点数超限：%d > %d" % (count, MAX_NODES))
    if depth > MAX_DEPTH:
        issues.add("$", "节点深度超限：%d > %d" % (depth, MAX_DEPTH))
    return count, depth


def main():
    parser = argparse.ArgumentParser(description="UI 文档离线校验（与 Swift UIDocumentValidator 同规则表）")
    parser.add_argument("path", nargs="?", help="UI 文档路径（main.json）")
    parser.add_argument("--frame", metavar="FILE", help="校验单帧 root（- 表示从 stdin 读取）")
    args = parser.parse_args()

    if not args.path and not args.frame:
        parser.print_help()
        return 2

    if args.frame:
        raw = sys.stdin.read() if args.frame == "-" else open(args.frame, "r", encoding="utf-8").read()
        payload = json.loads(raw)
        root = payload.get("root") if isinstance(payload, dict) and "root" in payload else payload
        issues = Issues()
        count, depth = verify_frame(root, issues)
        label = "帧 root"
    else:
        document = json.load(open(args.path, "r", encoding="utf-8"))
        issues = Issues()
        count, depth = verify_document(document, issues)
        label = args.path

    if issues:
        print("FAIL %s：%d 个问题" % (label, len(issues.items)))
        for item in issues.items:
            print("  - %s" % item)
        return 1
    print("OK %s：节点 %d 个、深度 %d 层、规则表校验通过" % (label, count, depth))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
