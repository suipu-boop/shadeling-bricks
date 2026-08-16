#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shadeling 内置可视化渲染器（零第三方依赖，仅标准库）。

生成可内联渲染的高质量 SVG 图，输出到 stdout。
支持四类图型 + 自动排版 + 多语言 CJK 宽度感知。

用法：
  python3 render_diagram.py --type flow --steps "A,B,C"
  python3 render_diagram.py --type flow --steps "隔离,改造,搬回" --subtitle "自我演化闭环"
  python3 render_diagram.py --type compare --cols "方案A,方案B" --rows "优点,风险" --cells '[["快","稳"]]'
  python3 render_diagram.py --type architecture --layers "UI层,Runtime层,数据层"
  python3 render_diagram.py --type matrix --rows "功能A,功能B" --cols "X,Y,Z" --cells '[[1,0,1],[0,1,1]]'
  echo '{"type":"flow","steps":["A","B"],"title":"流程"}' | python3 render_diagram.py --json -

设计规范（对标专业图表）：
  - 9 级颜色 ramp（每色 7 级明暗），50=最浅填充 / 600=强调色 / 800=正文
  - 标题 17px 500 weight / 副标题 13px 400 / 正文 14px 400
  - 圆角 rx=8(节点) / rx=12(卡片) / rx=20(外框)
  - 箭头 chevron head，stroke-width 1.5
  - 安全区 padding 40px
"""
from __future__ import annotations

import argparse
import json
import sys
from xml.sax.saxutils import escape


# ============================================================
#  颜色系统（9 色 × 7 级，与 Visualizer 设计规范对齐）
# ============================================================
_RAMP = {
    #   name      50(lt)  100     200     400(mid) 600(acc) 800(txt) 900(dk)
    "blue":   ("#E6F1FB","#B5D4F4","#85B7EB","#378ADD","#185FA5","#0C447C","#042C53"),
    "teal":   ("#E1F5EE","#9FE1CB","#5DCAA5","#1D9E75","#0F6E56","#085041","#04342C"),
    "coral":  ("#FAECE7","#F5C4B3","#F0997B","#D85A30","#993C1D","#712B13","#4A1B0C"),
    "purple": ("#EEEDFE","#CECBF6","#AFA9EC","#7F77DD","#534AB7","#3C3489","#26215C"),
    "green":  ("#EAF3DE","#C0DD97","#97C459","#639922","#3B6D11","#27500A","#173404"),
    "amber":  ("#FAEEDA","#FAC775","#EF9F27","#BA7517","#854F0B","#633806","#412402"),
    "red":    ("#FCEBEB","#F7C1C1","#F09595","#E24B4A","#A32D2D","#791F1F","#501313"),
    "gray":   ("#F1EFE8","#D3D1C7","#B4B2A9","#888780","#5F5E5A","#444441","#2C2C2A"),
}

def _c(name: str, level: int = 400) -> str:
    """取颜色 ramp 值。level: 50/100/200/400/600/800/900"""
    return _RAMP[name][[50,100,200,400,600,800,900].index(level)]

# 常用语义色快捷
BG_PRIMARY   = "#FFFFFF"       # 白底
BG_SECONDARY = _c("gray", 50)  # 浅灰面
BG_TERTIARY  = _c("gray", 100) # 页面背景
TEXT_PRIMARY = _c("gray", 900)
TEXT_SECONDARY= _c("gray", 600)
TEXT_MUTED   = _c("gray", 800)
STROKE_DEFAULT = _c("gray", 200)
STROKE_STRONG  = _c("gray", 400)

FONT = "system-ui, -apple-system, 'PingFang SC', 'Helvetica Neue', sans-serif"

# 固定画布宽度（适配 InlineWebView 680px viewBox）
CANVAS_W = 680
SAFE_X = 40
SAFE_X2 = CANVAS_W - SAFE_X  # 640
CONTENT_W = SAFE_X2 - SAFE_X  # 600


# ============================================================
#  文本工具
# ============================================================
def _est_width(s: str, cjk_px: float = 14.0, ascii_px: float = 8.0) -> float:
    """估算文本像素宽度（CJK 字符按 cjk_px，其余按 ascii_px）。"""
    w = 0.0
    for ch in s:
        w += cjk_px if ord(ch) > 0x2E80 else ascii_px
    return w


def _wrap_lines(text: str, max_w: float) -> list[str]:
    """按像素宽度折行（简单贪心）。返回行列表。"""
    words = text.replace("\n", " ").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip() if cur else w
        if _est_width(test) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ============================================================
#  SVG 原语
# ============================================================
class SVGBuilder:
    """流式 SVG 构建器，自动管理 defs / 尺寸 / 元素。"""

    def __init__(self, title: str = "", subtitle: str = ""):
        self._parts: list[str] = []
        self._h = 0  # 内容高度（不含 padding）
        self.title = title
        self.subtitle = subtitle

    def _defs(self) -> str:
        return (
            '<defs>'
            '<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M2 1L8 5L2 9" fill="none" stroke="{TEXT_MUTED}" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
            '</marker>'
            '</defs>'
        )

    def _header(self, total_h: int) -> str:
        y = 28
        parts: list[str] = []
        if self.title:
            parts.append(
                f'<text x="{SAFE_X}" y="{y}" font-family="{FONT}" font-size="17" '
                f'font-weight="500" fill="{_c("blue", 800)}">{escape(self.title)}</text>'
            )
            y += 24
        if self.subtitle:
            parts.append(
                f'<text x="{SAFE_X}" y="{y}" font-family="{FONT}" font-size="13" '
                f'fill="{TEXT_SECONDARY}">{escape(self.subtitle)}</text>'
            )
            y += 20
        return "".join(parts)

    def add(self, svg_fragment: str):
        self._parts.append(svg_fragment)

    def build(self, extra_bottom: int = 40) -> str:
        header_h = 0
        if self.title:
            header_h += 28 + 17 + 8  # y + font + gap
        if self.subtitle:
            header_h += 13 + 8 + 12
        total_h = header_h + self._h + extra_bottom
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
            f'viewBox="0 0 {CANVAS_W} {total_h}" font-family="{FONT}">',
            self._defs(),
            self._header(total_h),
            *self._parts,
            '</svg>',
        ]
        return "\n".join(out)


# ---------- 节点原语 ----------

def _rect(x: float, y: float, w: float, h: float,
          fill: str = BG_SECONDARY, stroke: str = STROKE_DEFAULT,
          sw: float = 0.5, rx: float = 8) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def _txt(x: float, y: float, text: str, size: int = 14,
         color: str = TEXT_PRIMARY, bold: bool = False,
         anchor: str = "middle") -> str:
    w = "500" if bold else "400"
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'font-weight="{w}" fill="{color}" text-anchor="{anchor}">'
            f'{escape(text)}</text>')


def _txt_multi(x: float, y_start: float, lines: list[str],
               size: int = 14, color: str = TEXT_PRIMARY,
               bold: bool = False, anchor: str = "middle",
               line_h: float = 20) -> str:
    """多行文本（居中或左对齐）。"""
    parts: list[str] = []
    for i, ln in enumerate(lines):
        parts.append(_txt(x, y_start + i * line_h, ln, size=size,
                          color=color, bold=bold, anchor=anchor))
    return "".join(parts)


def _chevron(x1: float, y1: float, x2: float, y2: float) -> str:
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{TEXT_MUTED}" stroke-width="1.5" '
            f'marker-end="url(#arrow)"/>')


def _dashed(x1: float, y1: float, x2: float, y2: float) -> str:
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{STROKE_DEFAULT}" stroke-width="0.5" '
            f'stroke-dasharray="4,3"/>')


# ---------- 节点组件 ----------

def _node(x: float, y: float, w: float, h: float,
          title: str, subtitle: str = "",
          color: str = "blue", filled: bool = True) -> str:
    """带标题+可选副标题的圆角节点。"""
    level = 100 if filled else 50
    fill = _c(color, level)
    stroke = _c(color, 600)
    parts = [_rect(x, y, w, h, fill=fill, stroke=stroke)]
    # 标题
    ty = y + h / 2 - (6 if subtitle else 0)
    parts.append(_txt(x + w / 2, ty, title, size=14,
                      color=_c(color, 800), bold=True))
    # 副标题
    if subtitle:
        parts.append(_txt(x + w / 2, ty + 18, subtitle, size=12,
                          color=TEXT_SECONDARY))
    return "".join(parts)


def _card(x: float, y: float, w: float, h: float,
          title: str = "", color: str = "gray") -> str:
    """大卡片容器（浅底+细边框）。"""
    parts = [_rect(x, y, w, h, fill=_c(color, 50),
                    stroke=_c(color, 200), rx=12)]
    if title:
        parts.append(_txt(x + 16, y + 22, title, size=14,
                           color=_c(color, 800), bold=True, anchor="start"))
    return "".join(parts)


# ============================================================
#  四种图型渲染器
# ============================================================

def render_flow(title: str, subtitle: str, steps: list[str]) -> str:
    """水平流程图：步骤节点 + chevron 箭头 + 可选副标题行。

    每个节点自动计算宽度（按最长文字），支持多行文字自动换行。
    """
    n = len(steps)
    node_h = 52
    gap = 40                    # 节点间距（含箭头）
    min_node_w = 120
    max_node_w = CONTENT_W // n - gap if n > 1 else CONTENT_W

    # 计算每个节点的实际宽度
    widths: list[float] = []
    for s in steps:
        ew = _est_width(s) + 40  # padding
        widths.append(max(min_node_w, min(max_node_w, ew)))

    content_w = sum(widths) + gap * (n - 1) if n > 1 else widths[0]
    start_x = SAFE_X + (CONTENT_W - content_w) / 2  # 居中

    b = SVGBuilder(title=title, subtitle=subtitle)

    # 绘制节点和箭头
    cx = start_x
    base_y = 0  # 相对偏移，build() 时加 header
    for i, s in enumerate(steps):
        w = widths[i]
        b.add(_node(cx, base_y, w, node_h, title=s, color="teal"))
        # 箭头
        if i < n - 1:
            ax1 = cx + w + 4
            ax2 = cx + w + gap - 4
            ay = base_y + node_h / 2
            b.add(_chevron(ax1, ay, ax2, ay))
        cx += w + gap

    b._h = base_y + node_h
    return b.build()


def render_compare(title: str, subtitle: str,
                  cols: list[str], rows: list[str],
                  cells: list[list]) -> str:
    """对比表：列头着色 + 行内容 + 行标签。

    不是死板表格，而是带圆角卡片的对比视图。
    """
    pad_x = SAFE_X
    card_pad = 16
    col_w = min(200, (CONTENT_W - pad_x * 2) // max(len(cols), 1))
    row_h = 48
    head_h = 42
    grid_w = col_w * len(cols)
    grid_h = head_h + row_h * len(rows)

    b = SVGBuilder(title=title, subtitle=subtitle)

    gy = 0  # grid Y offset from content top

    # 列头（彩色）
    palette = ["blue", "teal", "purple", "green", "amber", "coral"]
    for j, c in enumerate(cols):
        x = pad_x + j * col_w
        color = palette[j % len(palette)]
        b.add(_rect(x, gy, col_w, head_h, fill=_c(color, 100),
                     stroke=_c(color, 400), rx=8))
        b.add(_txt(x + col_w / 2, gy + head_h / 2 + 5, c,
                   size=14, color=_c(color, 800), bold=True))

    # 数据行
    for i, r in enumerate(rows):
        y = gy + head_h + i * row_h
        bg = BG_PRIMARY if i % 2 == 0 else _c("gray", 50)
        for j in range(len(cols)):
            x = pad_x + j * col_w
            val = ""
            if i < len(cells) and j < len(cells[i]):
                val = str(cells[i][j])
            b.add(_rect(x, y, col_w, row_h, fill=bg,
                         stroke=STROKE_DEFAULT, sw=0.3))
            if val:
                b.add(_txt(x + col_w / 2, y + row_h / 2 + 5, val,
                           size=13, color=TEXT_PRIMARY))
        # 行标签
        b.add(_txt(pad_x - 10, y + row_h / 2 + 5, r,
                   size=12, color=TEXT_MUTED, anchor="end"))

    b._h = gy + grid_h
    return b.build()


def render_architecture(title: str, subtitle: str,
                        layers: list[str]) -> str:
    """架构分层图：垂直堆叠的宽条，每层不同颜色，含嵌套标注。

    外层大圆角框包裹所有层。
    """
    pad = SAFE_X
    layer_h = 56
    layer_gap = 16
    outer_rx = 16
    inner_pad = 20

    total_layers_h = len(layers) * layer_h + (len(layers) - 1) * layer_gap
    box_w = CONTENT_W
    box_h = total_layers_h + inner_pad * 2

    b = SVGBuilder(title=title, subtitle=subtitle)

    by = 0  # outer box Y offset

    # 外框
    b.add(_rect(pad, by, box_w, box_h, fill=_c("blue", 50),
                 stroke=_c("blue", 200), rx=outer_rx))

    # 各层
    palette = ["blue", "teal", "purple", "green", "amber", "coral", "red"]
    ly = by + inner_pad
    for i, layer in enumerate(layers):
        color = palette[i % len(palette)]
        lx = pad + inner_pad
        lw = box_w - inner_pad * 2
        b.add(_rect(lx, ly, lw, layer_h, fill=_c(color, 100),
                     stroke=_c(color, 400), rx=8))
        b.add(_txt(lx + 16, ly + layer_h / 2 + 5, layer,
                   size=15, color=_c(color, 800), bold=True,
                   anchor="start"))
        ly += layer_h + layer_gap

    b._h = by + box_h
    return b.build()


def render_matrix(title: str, subtitle: str,
                  rows: list[str], cols: list[str],
                  cells: list[list]) -> str:
    """满足度矩阵：✓/✗/数字单元格着色，行标签 + 列头。

    ✓ → 绿底绿字  ✗ → 红底红字  数字/文字 → 白底黑字
    """
    pad_x = SAFE_X
    cell_w = min(140, (CONTENT_W - pad_x * 2) // max(len(cols), 1))
    cell_h = 46
    head_h = 40

    b = SVGBuilder(title=title, subtitle=subtitle)

    gy = 0

    # 列头
    for j, c in enumerate(cols):
        x = pad_x + j * cell_w
        b.add(_rect(x, gy, cell_w, head_h, fill=_c("gray", 100),
                     stroke=STROKE_STRONG, rx=6))
        b.add(_txt(x + cell_w / 2, gy + head_h / 2 + 4, c,
                   size=13, color=TEXT_PRIMARY, bold=True))

    # 单元格
    for i, r in enumerate(rows):
        y = gy + head_h + i * cell_h
        for j in range(len(cols)):
            x = pad_x + j * cell_w
            raw = ""
            if i < len(cells) and j < len(cells[i]):
                raw = cells[i][j]
            # 判断值类型
            if isinstance(raw, bool):
                raw = 1 if raw else 0
            raw_s = str(raw)
            if raw_s in ("1", "✓", "满足", "yes", "True", "OK"):
                fill, txt, tc = _c("green", 50), "✓", _c("green", 800)
            elif raw_s in ("0", "✗", "不满足", "no", "False", "—"):
                fill, txt, tc = _c("red", 50), "✗", _c("red", 800)
            elif raw_s in ("🟡", "半", "partial", "0.5"):
                fill, txt, tc = _c("amber", 50), "◐", _c("amber", 800)
            else:
                fill, txt, tc = BG_PRIMARY, raw_s, TEXT_PRIMARY
            b.add(_rect(x, y, cell_w, cell_h, fill=fill,
                         stroke=STROKE_DEFAULT, sw=0.3))
            b.add(_txt(x + cell_w / 2, y + cell_h / 2 + 4, txt,
                       size=15 if len(txt) <= 2 else 13,
                       color=tc, bold=(len(txt) <= 2)))
        # 行标签
        b.add(_txt(pad_x - 10, y + cell_h / 2 + 4, r,
                   size=12, color=TEXT_MUTED, anchor="end"))

    b._h = gy + head_h + len(rows) * cell_h
    return b.build()


def render_timeline(title: str, subtitle: str, events: list) -> str:
    """垂直时间线：中轴 + 事件卡片左右交替。

    events: [{date, title, desc?}]，date 为日期/时间字符串，title 为事件名。
    """
    b = SVGBuilder(title=title, subtitle=subtitle)
    axis_x = CANVAS_W / 2
    n = len(events)
    row_h = 66
    dot_r = 5
    card_w = CONTENT_W * 0.42
    card_h = 44

    b.add(f'<line x1="{axis_x:.1f}" y1="0" x2="{axis_x:.1f}" '
          f'y2="{n * row_h:.1f}" stroke="{STROKE_DEFAULT}" stroke-width="1.5"/>')

    for i, ev in enumerate(events):
        left = (i % 2 == 0)
        cy = i * row_h + row_h / 2
        # 圆点
        b.add(f'<circle cx="{axis_x:.1f}" cy="{cy:.1f}" r="{dot_r}" '
              f'fill="{_c("teal", 600)}" stroke="#fff" stroke-width="1.5"/>')
        # 卡片
        cx0 = SAFE_X if left else SAFE_X2 - card_w
        b.add(_rect(cx0, cy - card_h / 2, card_w, card_h,
                    fill=_c("blue", 50), stroke=_c("blue", 200), rx=8))
        # 日期 + 标题
        b.add(_txt(cx0 + card_w / 2, cy - 6, str(ev.get("date", "")),
                   size=11, color=TEXT_SECONDARY))
        b.add(_txt(cx0 + card_w / 2, cy + 12, str(ev.get("title", "")),
                   size=13, color=_c("blue", 800), bold=True))

    b._h = n * row_h
    return b.build()


def render_gantt(title: str, subtitle: str, tasks: list) -> str:
    """横向甘特图：左侧任务名 + 右侧时间条。

    tasks: [{name, start, end, progress?}]，start/end 为可比较数值（如天数/日期戳）。
    """
    b = SVGBuilder(title=title, subtitle=subtitle)
    label_w = 180
    chart_x = SAFE_X + label_w
    chart_w = CONTENT_W - label_w
    row_h = 36
    n = len(tasks)

    starts = [t.get("start", 0) for t in tasks]
    ends = [t.get("end", 0) for t in tasks]
    t0 = min(starts) if starts else 0
    t1 = max(ends) if ends else 1
    span = max(t1 - t0, 1)

    def _x(v: float) -> float:
        return chart_x + (v - t0) / span * chart_w

    for i, t in enumerate(tasks):
        y = i * row_h
        # 任务名
        b.add(_txt(SAFE_X, y + row_h / 2 + 4, str(t.get("name", "")),
                   size=13, color=TEXT_PRIMARY, anchor="start"))
        # 背景轨道
        b.add(_rect(chart_x, y + 6, chart_w, row_h - 12,
                    fill=BG_SECONDARY, stroke=STROKE_DEFAULT, rx=6))
        # 时间条
        x0 = _x(t.get("start", t0))
        x1 = _x(t.get("end", t1))
        w = max(x1 - x0, 4)
        b.add(_rect(x0, y + 6, w, row_h - 12,
                    fill=_c("teal", 400), stroke=_c("teal", 600), rx=6))
        # 进度百分比
        pct = t.get("progress")
        if pct is not None:
            b.add(_txt(x0 + w / 2, y + row_h / 2 + 4, f"{pct}%",
                       size=11, color="#FFFFFF"))

    b._h = n * row_h
    return b.build()


# ============================================================
#  入口 & 参数解析
# ============================================================

def _build(args) -> str:
    """根据参数构建 SVG 字符串。"""
    # JSON 输入优先
    data: dict = {}
    if args.json and args.json != "-":
        data = json.loads(args.json)
    elif args.json == "-":
        data = json.load(sys.stdin)

    t = args.type or data.get("type", "")
    title = args.title or data.get("title", "")
    subtitle = args.subtitle or data.get("subtitle", "")

    if t == "flow":
        steps = args.steps or data.get("steps", [])
        return render_flow(title, subtitle, [str(s) for s in steps])

    if t == "compare":
        cols = args.cols or data.get("cols", [])
        rows = args.rows or data.get("rows", [])
        cells = args.cells or data.get("cells", [])
        return render_compare(title, subtitle, cols, rows, cells)

    if t == "architecture":
        layers = args.layers or data.get("layers", [])
        return render_architecture(title, subtitle, [str(x) for x in layers])

    if t == "matrix":
        rows = args.rows or data.get("rows", [])
        cols = args.cols or data.get("cols", [])
        cells = args.cells or data.get("cells", [])
        return render_matrix(title, subtitle, rows, cols, cells)

    if t == "timeline":
        events = args.events if getattr(args, "events", None) else data.get("events", [])
        return render_timeline(title, subtitle, events)

    if t == "gantt":
        tasks = args.tasks if getattr(args, "tasks", None) else data.get("tasks", [])
        return render_gantt(title, subtitle, tasks)

    raise SystemExit(f"未知类型 --type='{t}'，须为 flow / compare / architecture / matrix / timeline / gantt")


def main():
    ap = argparse.ArgumentParser(
        description="Shadeling 内置可视化 SVG 渲染器（高质量版）")
    ap.add_argument("--type", required=True,
                    help="图型: flow / compare / architecture / matrix / timeline / gantt")
    ap.add_argument("--title", default="", help="主标题")
    ap.add_argument("--subtitle", default="", help="副标题")
    ap.add_argument("--steps", help="逗号分隔步骤（flow）")
    ap.add_argument("--layers", help="逗号分隔层名（architecture）")
    ap.add_argument("--cols", help="逗号分隔列名（compare/matrix）")
    ap.add_argument("--rows", help="逗号分隔行名（compare/matrix）")
    ap.add_argument("--cells", help="JSON 二维数组（compare/matrix）")
    ap.add_argument("--events", help="JSON 数组（timeline）")
    ap.add_argument("--tasks", help="JSON 数组（gantt）")
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    help="从参数字符串或 stdin(-) 读 JSON 对象")
    args = ap.parse_args()

    # 逗号分隔参数展开为列表
    for attr in ("steps", "layers", "cols", "rows"):
        v = getattr(args, attr, None)
        if v:
            setattr(args, attr, [s.strip() for s in v.split(",") if s.strip()])

    if args.cells:
        try:
            args.cells = json.loads(args.cells)
        except json.JSONDecodeError:
            args.cells = []

    for attr in ("events", "tasks"):
        v = getattr(args, attr, None)
        if v:
            try:
                setattr(args, attr, json.loads(v))
            except json.JSONDecodeError:
                setattr(args, attr, [])

    print(_build(args))


if __name__ == "__main__":
    main()
