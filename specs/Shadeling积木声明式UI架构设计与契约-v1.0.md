---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_4316f6d2c31911f1884b525400cd780f
    ReservedCode1: gqLi9cKxBtViWtsVUGj9uO3QPklt2quHpQtVi+dqXz/NHAJvxswpieTwHGMcYqX/83dkJF5rxjOE7qdRu9iRqNv1jjCOk2dgAEOB+wvKMg7/Or6b2T9YjYALDgw1wLXlu1D6B/qPQ4nR0KygZodhKFg8dwO9ZAqlJycSZG2FzUqVzEmqsBFUj4aN4j4=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_4316f6d2c31911f1884b525400cd780f
    ReservedCode2: gqLi9cKxBtViWtsVUGj9uO3QPklt2quHpQtVi+dqXz/NHAJvxswpieTwHGMcYqX/83dkJF5rxjOE7qdRu9iRqNv1jjCOk2dgAEOB+wvKMg7/Or6b2T9YjYALDgw1wLXlu1D6B/qPQ4nR0KygZodhKFg8dwO9ZAqlJycSZG2FzUqVzEmqsBFUj4aN4j4=
---







# Shadeling 积木声明式 UI 架构设计与契约 v1.0

> **状态**：方向已拍板（2026-09-26）；**v1.0（2026-10-09）**：Phase E 收口，随 legacy 独立 .app 路径删除升版——退役执行记录见 §6.4，Phase E 验收结论见 §7.6。实现变更须同步本文。
> **适用范围**：Shadeling 底座（主区域宿主、渲染器、协议、闸门、安装器）、第三方积木包、积木市场。
> **关联文档**：《积木规范化模板规格 v0.1》《积木市场 V2：独立积木包 + 真实下载安装》《brick-agent-bridge v0》《ipc-schema-v0》。
> **本文性质**：契约文档。只定义"应当是什么"，不含实现排期细节（实施计划见第七章）。

## 摘要

用户已拍板：积木形态由「独立 .app + 自开窗口」改为「内嵌底座主区域」，第三方通道采用**声明式 UI**。本文是该架构的完整契约，覆盖八章：

| 章 | 主题 | 核心结论 |
|---|---|---|
| 一 | 总体架构分层 | 三层架构：底座宿主层（唯一窗口主体）/ 渲染层（主进程内）/ 逻辑进程层（每积木 1 个无窗口子进程）；状态归逻辑进程，界面为状态快照 |
| 二 | 声明式 UI 格式与组件清单 | 采用 JSON 节点树（`shadeling-ui/1`）+ 受限插值 + 事件上报；首批 10 类组件，逐项给出能力边界与不支持场景 |
| 三 | manifest v2 字段定义 | `brick-app/v2` 以 `ui` + `logic` 双入口替代 `bundle`；`views[]` 收敛为 `nav`；权限与配额显式声明 |
| 四 | 底座与逻辑进程协议 | stdio 上 LSP 风格长度前缀帧的 JSON-RPC；能力调用复用既有闸门与白名单；新增 `430x` 错误码段与崩溃恢复机制 |
| 五 | 权限与配额模型 | 三层权限模型（声明 / 授予 / 校验），默认拒绝；高危标红 + 二次确认；新增配额只可收紧不可放宽 |
| 六 | 与现有资产的关系 | BrickUIKit 令牌与组件层完全复用，BrickScene / 独立窗口 / 桥 token 注入退役；注册表红线不变 |
| 七 | 分阶段实施计划与验收 | Phase A~E（相对周次 W1~W16），每阶段带可测验收标准、量化指标、回滚与风险预案 |
| 八 | vault 与 wechat-mp 迁移评估 | vault 可全量迁移（无硬瓶颈）；wechat-mp 部分迁移，Markdown 渲染与 HTML 预览为硬瓶颈，建议延后 |

**一句话总纲**：底座是唯一的窗口与渲染主体，积木退化为「声明式 UI 描述 + 独立逻辑进程」；安全边界由进程隔离 + 底座能力闸门共同保证，视觉一致性由 BrickUIKit 令牌强制。

## 目录

- [一、总体架构分层](#一总体架构分层)
- [二、声明式 UI 描述格式与首批组件清单](#二声明式-ui-描述格式与首批组件清单)
- [三、积木 manifest v2 字段定义](#三积木-manifest-v2-字段定义)
- [四、底座与逻辑进程协议（JSON-RPC over stdio）](#四底座与逻辑进程协议json-rpc-over-stdio)
- [五、权限与配额模型](#五权限与配额模型)
- [六、与现有资产的关系及演进退役方案](#六与现有资产的关系及演进退役方案)
- [七、分阶段实施计划与验收](#七分阶段实施计划与验收)
- [八、vault 与 wechat-mp 迁移可行性评估](#八vault-与-wechat-mp-迁移可行性评估)

## 术语表

| 术语 | 含义 |
|---|---|
| 底座（Host） | Shadeling.app 主进程：窗口、主区域槽位、渲染器、能力闸门、安装器 |
| 积木（Brick） | 可安装的功能单元；v2 形态 = 声明式 UI 文档 + 逻辑进程 + manifest v2 |
| 逻辑进程（Logic Process） | 每积木 1 个无窗口子进程，持有业务状态，经 stdio 与底座通信 |
| 渲染器（Renderer） | 底座主进程内模块，解释 UI 文档并构建视图、采集事件 |
| UI 文档 | JSON 节点树，schema 固定为 `shadeling-ui/1` |
| 能力（Capability） | 底座代理的受控外部能力（主模型、联网检索、文件读取、浏览器操作等） |
| 闸门（Gate） | 能力调用统一入口，执行「已声明 → 已授予 → 未超配额」三重校验 |
| 槽位（Slot） | 主区域中一个积木占用的位置，天然单实例 |
| 快照（Snapshot） | 逻辑进程下发的界面描述（全量 / 增量 / 状态局部） |
| 令牌（Token） | BrickUIKit 中的设计变量（颜色 / 字号 / 间距 / 圆角），UI 文档仅可引用令牌名 |

---
# 一、总体架构分层

> 状态：**方向已拍板，契约待评审**（2026-09-26）
> 权威实现：Shadeling app（渲染器 / 协议 / 安装器）+ 本仓库（积木包发布区）
> 关联契约：《积木规范化模板规格 v0.1》《积木市场 V2：独立积木包 + 真实下载安装》《brick-agent-bridge v0》《ipc-schema-v0》
> 本文是「第三方积木声明式 UI 通道」的契约文档；实现变更须同步本文。

## 1.1 形态变更结论

积木交付形态由「独立 .app + 自开窗口」重构为「内嵌底座主区域 + 声明式 UI 描述 + 独立逻辑进程」。变更前后对照：

| 维度 | 旧形态（v1：独立 .app） | 新形态（v2：内嵌声明式） |
|---|---|---|
| 交付物 | `.app` bundle，manifest 以 `bundle` 指向 | 无窗口积木包：`manifest.json` + `ui/*.json` + `logic/*` |
| 窗口 | 积木自建窗口（BrickScene 980×680，最小 760×520） | 底座主区域槽位，宿主外壳统一提供标题、返回与关闭 |
| UI 技术 | 积木自绘 SwiftUI，靠 BrickUIKit 自觉对齐视觉 | 底座渲染器解释声明式 UI，视觉由令牌强制，无自由绘制 |
| 进程 | 每积木 1 个 GUI 进程，可多实例 | 每积木 1 个无窗口逻辑进程，主区域槽位天然单实例 |
| 通信 | 应用级 IPC（`host:port` + 环境变量注入 token，通道本身无鉴权） | 逻辑进程 stdio 上的 JSON-RPC，能力调用统一过底座闸门 |
| 第三方门槛 | 需 macOS 开发签名、公证、独立出包 | 提交 UI 描述与逻辑脚本，无需自建窗口与签名流程 |
| 安全边界 | 进程隔离 + 桥方法白名单 | 进程隔离 + 能力闸门 + 无网络/文件直连 + UI 静态可审计 |

**保留不变的约束**：进程级隔离、能力白名单（`brick_agent_*` 三方法及既有桥权限枚举）、安装时权限确认与高危标红、`429x` 配额口径、主模型全局占用上限。

## 1.2 三层架构

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1 底座宿主层  Shadeling.app（主进程，唯一窗口主体）                  │
│   主窗口：左栏 Sidebar │ mainArea 主区域 │ 右栏 ContextPanel          │
│   ├─ 主区域槽位：工坊(showWorkshop) / 积木宿主(activeBrickSlot) / 详情页   │
│   ├─ BrickHostView（宿主外壳：标题栏 + 返回/关闭 + 崩溃态容器）        │
│   ├─ 能力闸门 BrickPermissionGate（白名单 + 配额 + 鉴权）             │
│   ├─ 逻辑进程托管 BrickProcessSupervisor（spawn / 心跳 / 回收）        │
│   └─ 安装器 / 市场 / 权限确认 UI                                      │
├──────────────────────────────────────────────────────────────────────┤
│ L2 渲染层  BrickRenderer（主进程内，无独立进程）                       │
│   ├─ UI 文档校验器（schema / 白名单 / 限额）                          │
│   ├─ 视图构建器（JSON 节点树 → SwiftUI 视图，复用 BrickUIKit 令牌）    │
│   ├─ 事件采集器（tap / change / submit / select / appear）            │
│   └─ 弹层托管（sheet / dialog / banner，复用既有三契约语义）           │
├──────────────────────────────────────────────────────────────────────┤
│ L3 逻辑进程层  每积木 1 个独立子进程（无窗口、无 UI 权限）             │
│   ├─ 业务状态机（唯一状态源）                                        │
│   ├─ UI 快照生成（render(state)）                                    │
│   └─ 能力调用发起（capability/call → 底座闸门）                       │
└──────────────────────────────────────────────────────────────────────┘
        L2 ⇄ L3：stdin/stdout 上的 JSON-RPC（本文第四章）
```

### 三层职责与不可越界项

| 层 | 承载 | 职责 | 明确不做 |
|---|---|---|---|
| L1 底座宿主层 | 主进程 | 窗口与主区域槽位、导航、宿主外壳、安装与市场、权限确认、能力闸门与配额裁决、逻辑进程生命周期托管、崩溃态呈现 | 不解释积木业务语义，不代积木持有业务状态 |
| L2 渲染层 | 主进程内模块 | 校验并解释 UI 文档、构建视图、采集并上报事件、应用状态快照、托管弹层与横幅、呈现错误态 | 不执行任何业务逻辑、不直接发起能力调用、不执行 UI 描述中的代码 |
| L3 逻辑进程层 | 独立子进程 | 持有业务状态、处理事件、产出 UI 快照、经闸门发起能力调用 | 不开窗口、不直连网络、不越过私有目录读写文件、不渲染 |

## 1.3 进程与线程拓扑

| 归属 | 单元 | 数量 | 说明 |
|---|---|---|---|
| 主进程 | 主线程 | 1 | SwiftUI 渲染与窗口事件 |
| 主进程 | 协议读循环 | 每积木 1 个串行队列 | 解析 stdout 帧，投递到主线程应用快照 |
| 主进程 | 进程监督 | 1（GCD 定时器） | 心跳超时、退出码捕获、重启策略 |
| 逻辑进程 | 主循环 | 每积木 1 个进程 | 读 stdin 帧 → 处理 → 写 stdout 帧；stderr 直通底座日志 |

**主区域槽位与单实例**：一个 `brick_id` 在主区域最多占 1 个槽位，重复点击入口只做「激活并置前」，不新建进程——该语义替代旧 `runningBricks` 的多实例登记表，登记表保留用于逻辑进程句柄管理。

## 1.4 状态所有权与刷新方向

采用**单向下行 + 单向上行**，不引入双向绑定：

| 方向 | 内容 | 载体 |
|---|---|---|
| 下行 | 状态快照 → 界面 | 逻辑进程发 `ui/update`（全量快照或路径 patch），携带单调递增 `state_version` |
| 上行 | 用户交互 → 逻辑进程 | 渲染器发 `event/dispatch`（`node_id` / `event` / `payload` / `ui_state`） |
| 旁路 | 能力调用 | 逻辑进程发 `capability/call`，底座闸门裁决后回 `capability/result` |

约定：

1. **唯一状态源在逻辑进程**。渲染器不持有业务状态，仅保留瞬时 UI 状态（焦点、滚动位置、未提交的输入草稿），并在事件中回传给逻辑进程。
2. **界面是状态的函数**：`view = render(state)`。逻辑进程收到事件后更新 state 并推送新快照，渲染器只负责应用快照。
3. **乱序保护**：渲染器丢弃 `state_version` 小于等于当前值的快照；逻辑进程丢弃携带过期 `state_version` 的事件。
4. **崩溃不丢槽位**：逻辑进程崩溃时渲染器保留最后一次有效界面并叠加崩溃态，槽位、导航位置、`brick_id` 均不变。

## 1.5 隔离与信任边界

| 资源 / 能力 | 旧形态可达性 | 新形态可达性 | 通道与前提 |
|---|---|---|---|
| 窗口与 UI | 自开窗口 | 仅主区域 | 渲染器（无窗口 API 暴露） |
| 网络 | 直连（应用级 `network` 声明） | **不可直连** | `agent.web`（联网检索，只读抓取） |
| 文件系统 | 直连（用户级权限） | 仅积木私有数据目录 | 私有目录直读写；其他路径需 `agent.fs.read` 或新增 `fs.pick`；`fs.pick` 返回的路径视为该次会话内用户已授权（E1 前置 T1，2026-10-08）：逻辑进程可直接读取其内容，读取范围不得超出所选路径，越界读仍计违规并审计 |
| 浏览器 / 本机界面 | 可（Accessibility） | **默认拒绝** | `agent.browser` / `agent.local`（高危，安装时标红） |
| 主模型 | 经桥 | 经闸门 | `agent.chat`（无工具） |
| 系统通知 / 剪贴板 | 可 | 默认拒绝 | 新增 `notify` / `ui.clipboard.write`（见第五章） |
| 本地生物识别 | 可 | 默认拒绝 | 新增 `auth.biometric`（见第八章瓶颈项） |

## 1.6 架构红线（实现与评审必查）

- **R1** 逻辑进程不得创建窗口、不得调用应用激活类 API。
- **R2** 逻辑进程不得直连网络；网络能力一律经底座闸门代理并计入配额。
- **R3** 渲染器不得执行 UI 文档中的任意代码：表达式求值仅限白名单插值与格式化器，禁止脚本、循环、函数调用。
- **R4** 逻辑进程不得读写底座数据目录与其他积木私有目录，仅可访问自身私有目录。
- **R5** 单积木崩溃不得影响底座进程与其他积木：崩溃限于槽位内呈现，可原地重启。
- **R6** UI 文档不得引用远程资源；图片仅限包内资源或底座代理的受控本地资源。
- **R7** 权限与配额在 manifest 中显式声明、默认拒绝；安装时确认 + 运行时再校验双闸门，缺一不可。

## 1.7 本章决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| A1 | 渲染在主进程内实现，逻辑进程独立 | 复用 BrickUIKit 令牌与组件，避免跨进程渲染带来的输入法与无障碍损失 |
| A2 | 状态归逻辑进程，界面为快照 | 避免双向绑定与共享内存带来的竞态、审计困难 |
| A3 | 逻辑进程与底座用 stdio 而非本地 socket | 进程生命周期天然绑定、无需端口与额外鉴权面（见第四章） |
| A4 | 主区域槽位天然单实例，替代旧多实例登记 | 内嵌形态下重复入口只需激活置前，无需第二进程 |
| A5 | 能力调用沿用既有闸门与权限枚举 | 复用已验证的白名单、标红与 429x 配额口径，降低安全返工 |
# 二、声明式 UI 描述格式与首批组件清单

## 2.1 格式选型与取舍

| 候选方案 | 优势 | 否决理由 |
|---|---|---|
| HTML / CSS / JS + WKWebView | 表达力最强，生态成熟 | 与底座视觉割裂；需 JS 沙箱与额外安全审计；内存与启动成本高；无法复用 BrickUIKit 令牌；事件语义与原生导航难对齐 |
| 下发 SwiftUI 源码并动态编译 | 组件复用度最高 | 等于任意代码执行，无法静态审计；崩溃面覆盖主进程；与底座版本强绑定 |
| 远程渲染（服务端出图，客户端显示位图） | 隔离最强 | 交互延迟、无法文本选择与无障碍、带宽与离线不可用 |
| **JSON 声明式节点树（采用）** | 可静态审计、属性白名单、视觉可控、跨版本稳定 | 表达力受限——本文以「不支持清单」显式封边（§2.6） |

**结论**：采用 JSON 节点树 + 受限插值 + 事件上报的纯声明格式；表达力不足的场景不做隐式兼容，一律显式列为不支持并提供替代路径。

## 2.2 UI 文档结构

```json
{
  "schema": "shadeling-ui/1",
  "version": 1,
  "root": {
    "type": "container",
    "id": "root",
    "props": { "direction": "vertical", "gap": 16, "padding": 20 },
    "children": [ ]
  }
}
```

| 顶层字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema` | string | 是 | 固定 `shadeling-ui/1`；不匹配则整帧拒绝 |
| `version` | int | 是 | 文档结构版本，用于渲染器向后兼容判断 |
| `root` | object | 是 | 根节点，必须为容器类节点 |
| `state_snapshot` | object | 否 | 随帧下发的状态（仅用于插值求值，渲染器不持久化） |

## 2.3 节点模型

### 通用字段

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `type` | string | 是 | 必须在组件白名单内，未知类型 → 整帧拒绝 |
| `id` | string | 是 | `^[a-z][a-z0-9_]{0,63}$`，同一帧内唯一 |
| `props` | object | 否 | 键必须在组件属性白名单内，未知键 → 整帧拒绝 |
| `children` | array | 否 | 仅容器类节点可携带；叶子节点携带 → 整帧拒绝 |
| `if` | string | 否 | 受限布尔插值（如 `{{state.has_error}}`），为假时节点不渲染 |
| `on` | object | 否 | 事件绑定，键为事件名，值为动作名（见 §2.4） |

### 样式与布局规则

- **样式只允许引用令牌**：颜色 / 字号 / 间距 / 圆角 / 阴影一律使用令牌名（如 `text.primary`、`surface.card`、`space.md`、`radius.md`），不接受自由色值、字号数值、渐变。
- **三级前景降级口径（E1 前置 T2，2026-10-08）**：颜色令牌表不含 `text.tertiary`；原设计的第三级前景（列表 meta、次要说明等）一律降级为 `text.secondary`，不新增令牌（`surface.inset` 是背景色，不可用于前景）。
- **布局原语**：`container(direction/gap/padding/align/size)`、`grid(columns/min_column_width/gap)`、`scroll(axis)`、`spacer`；尺寸取值 `hug` / `fill` / 数值 pt。
- **禁止项**：绝对定位、z-index 叠层、自定义绘制、动画时间线、变换矩阵。

## 2.4 数据绑定与事件

### 插值语法

- 形式：`{{state.<path>}}`，`<path>` 仅支持点号路径（如 `state.draft.title`）。
- 格式化器（可选）：`{{state.created_at | date}}`、`{{state.size | bytes}}`、`{{state.ratio | percent}}`、`{{state.count | number}}`。
- **禁止**：算术运算、字符串拼接、函数调用、条件表达式、索引计算、访问 `state` 以外的作用域。

### 布尔位（busy / disabled / visible / danger / required / mono）

- **定义**：`button.busy`、`button.disabled`、`overlay.visible`、`overlay.danger`、`form.fields[].required`、`form.fields[].disabled`、`form.fields[].mono`（仅 `textarea`）为**布尔位**——渲染取值与校验口径同源（Swift `Interpolation.boolSlot` ↔ `verify_ui_doc.py::_check_bool_slot`）。
- **合法取值**（仅三种，其余一律 `4303`）：
  1. 布尔字面量：`true` / `false`；
  2. 受限布尔插值：`{{state.<path>}}`（严格单表达式，**不接格式化器**、不允许字面量拼接）；
  3. 旧式裸路径：`state.<path>`（**仅 legacy 兼容**，新内容一律写形态 2）。
- **求值**：按 `truthy` 口径——`bool` 取自身；数值非 0；字符串/数组/对象非空；`null` 与缺失为假。
- **与 `if` 的关系**：`if` 同属受限布尔插值（§2.3 通用字段），两者共用同一语法与求值口径；`if` 为假时节点不渲染，布尔位为假时控件呈禁用/占位态。
- **失败前置**：装机期校验由宿主 `BrickInstallGate → UIDocumentValidator.boolProp` 执行（`4303`）；**打包期**由 `scripts/pack_product.py::_gate_ui_document` 先跑同源规则表（`verify_ui_doc.py`），带病内容**拒出包**，不再留到装机才炸。

### 事件上行

| 事件名 | 触发时机 | payload |
|---|---|---|
| `tap` | 按钮 / 卡片 / 列表项点击 | 空 |
| `change` | 输入框、开关、选择器值变化（失焦或确认时） | `{ "value": <string\|bool\|number> }` |
| `submit` | 表单提交（按钮或回车） | `{ "fields": { "<field_id>": <value> } }` |
| `select` | 列表 / 分段选择 | `{ "index": <int>, "key": <string> }` |
| `appear` | 节点首次进入视口 | 空 |

事件信封统一携带 `ui_state`（瞬时 UI 状态回传：`focused_id`、`scroll_y`、`draft_text`），供逻辑进程在重渲染后恢复焦点与滚动。

**无双向绑定**：输入框显示值由 `state` 决定；用户输入先在渲染器本地缓存，`change` / `submit` 时上报，逻辑进程更新 state 后以新快照覆盖。

**去抖归属（E1 前置 T5，2026-10-08）**：渲染器**不做**任何去抖 / 节流，输入每次变化即时上抛 `change`（受全局 30 次/秒额度约束，超额丢弃 + `4306`）；高频输入的合并与去抖由**逻辑进程**负责（建议 250~300 ms 窗口 + 单飞），搜索类输入尤其如此。

## 2.5 首批组件清单（能力边界）

### 1. container

| 项 | 内容 |
|---|---|
| 关键 props | `direction`(horizontal/vertical)、`gap`、`padding`、`align`、`size`、`background`(令牌)、`card_style` |
| 事件 | 无（点击语义请用 button/card） |
| 支持 | 分栏、分组、滚动容器、间距与内边距、卡片式背景 |
| **不支持** | 绝对定位、叠层、分割线之外的装饰性绘制 |

### 2. text

| 项 | 内容 |
|---|---|
| 关键 props | `value`(插值)、`style`(title/heading/body/caption/label)、`color`(令牌)、`lines`(最大行数)、`truncate`(**枚举** `tail`/`middle`，布尔为 legacy 兼容)、`mono`(布尔位，§2.4)、`badge` |
| 事件 | 无 |
| 支持 | 单/多行文本、截断、等宽数字与代码片段、行内徽标 |
| **不支持** | Markdown / HTML 富文本渲染、内联图片、自定义字体、文本内链接跳转、文本选择复制（列表与详情页的复制请用 `button` + `ui.clipboard.write`） |

### 3. button

| 项 | 内容 |
|---|---|
| 关键 props | `label`、`style`(primary/secondary/ghost/danger)、`icon`(内置图标名)、`busy`(布尔位，§2.4)、`disabled`(布尔位，§2.4)、`size`(sm/md) |
| 事件 | `tap` |
| 支持 | 图标 + 文字、忙碌态（由 state 驱动）、禁用态、危险动作语义色 |
| **不支持** | 自定义尺寸与图标位置微调、长按手势、右键菜单、拖拽、按钮内自定义视图组合 |

### 4. list

| 项 | 内容 |
|---|---|
| 关键 props | `items`(插值数组)、`item_template`(节点模板)、`selection`(none/single)、`empty_state`(文本/节点)、`lazy`(bool) |
| 事件 | `select`、`tap`（项内按钮） |
| 支持 | 静态/动态列表、空态、单选、懒加载（上限 5000 行）、行内操作按钮 |
| **不支持** | 拖拽排序、多选批量操作、树形嵌套、表头冻结、单元格内自定义绘制、无限滚动分页（分页请由逻辑进程按需追加 items） |

### 5. card

| 项 | 内容 |
|---|---|
| 关键 props | `title`、`subtitle`、`meta`(相对时间等)、`tags`(数组)、`badge`、`icon`、`thumbnail`、`actions`(按钮数组)、`selectable` |
| 事件 | `tap`、`select` |
| 支持 | 卡片墙基本单元、标签与徽标、缩略图、悬浮高亮（由渲染器统一提供） |
| **不支持** | 自定义阴影/圆角/渐变、卡片内自由布局、卡片间拖拽重排、3D 翻转等动效 |

### 6. form

| 项 | 内容 |
|---|---|
| 子类型 | `field`(单行输入)、`textarea`(多行)、`picker`(下拉/分段/日期，`mode=menu/segment/date`)、`toggle`、`checkbox`、`secret`(掩码输入) |
| 关键 props | `field_id`、`label`、`placeholder`、`value`(插值)、`options`、`error`(错误文案)、`required`(布尔位，§2.4)、`disabled`(布尔位，§2.4)；`mono`(布尔位，仅 `textarea`，等宽输入，E1 前置 T4) |
| 事件 | `change`、`submit`；`textarea` 逐次输入即上抛 `change`（E1 前置 T5） |
| 支持 | 常见表单、字段级错误提示（文案由逻辑进程返回）、必填标记、日期选择（`picker mode=date`） |
| **不支持** | 富文本编辑、Markdown 实时预览、自动完成/联想下拉、多文件上传控件、字段联动计算（联动由逻辑进程重渲染实现）、输入掩码与正则即时校验 |

### 7. icon

| 项 | 内容 |
|---|---|
| 关键 props | `name`、`size`(sm/md/lg)、`color`(令牌) |
| 支持 | SF Symbols 白名单子集 + 底座内置图标集；与文字并排；白名单 E1 前置（2026-10-08，T3）增补 2 个：`tray`、`photo.on.rectangle.angled` |
| **不支持** | 自定义 SVG / 位图图标、多色图标、图标动画 |

### 8. progress

| 项 | 内容 |
|---|---|
| 关键 props | `style`(linear/circular/spinner)、`value`(0~1，插值)、`indeterminate`(bool)、`label` |
| 支持 | 确定性进度、不确定态加载、步骤标签 |
| **不支持** | 自定义动画曲线与颜色、多段进度条、环形刻度绘制 |

### 9. overlay（弹层）

| 子类型 | 语义 | 关键 props |
|---|---|---|
| `sheet` | 侧滑/上滑表单面板（沿用 `.brickSheet` 契约） | `title`、`content`、`primary_action`、`secondary_action`、`width` |
| `dialog` | 确认对话框（沿用 `.brickConfirm` 契约） | `title`、`message`、`confirm_label`、`cancel_label`、`danger` |
| `banner` | 顶部横幅（沿用 `BrickBanner` 契约） | `text`、`level`(info/success/warning/error)、`auto_dismiss_ms` |
| `toast` | 轻提示 | `text`、`duration_ms` |

**子类载体（E1 收口，2026-10-08）**：子类型一律写在 `props.kind`（上表四个取值），节点**顶层** `subtype` 键已废弃——`verify_ui_doc.py` 将顶层 `subtype` 判为错误（唯一载体口径），`verify_products.py` 亦只认 `props.kind`；存量冗余已清理（`products/vault/ui/main.json` 6 处）。

**`visible` 口径（2026-10-09 补）**：`visible` 为**布尔位**（可省略；省略时按子类型默认——`sheet`/`dialog` 由逻辑进程 `state` 驱动显隐，`banner`/`toast` 默认随帧呈现）。合法取值仅布尔字面量、受限布尔插值 `{{state.<path>}}`、旧式裸路径 `state.<path>`（legacy），细则见 §2.4「布尔位」；`danger` 同为布尔位。

| 项 | 内容 |
|---|---|
| 支持 | 单一弹层同时可见、模态遮罩、危险动作红色确认、自动消失横幅 |
| **不支持** | 弹层嵌套、非模态悬浮窗、自定义遮罩与转场动画、跟随鼠标的浮层、系统级面板（NSOpenPanel 需 `fs.pick` 能力） |

### 10. image

| 项 | 内容 |
|---|---|
| 关键 props | `source`(包内相对路径 / 底座受控资源句柄)、`fit`(fill/fit)、`height`、`placeholder`、`fallback_text` |
| 支持 | 包内资源、底座代理的本地缩略图（经能力返回句柄）、占位与失败态 |
| **不支持** | 远程 URL 直连、滤镜/裁剪/旋转等图像处理、图片编辑、GIF 播放（动图请用 `progress` 或静态首帧）、自定义圆角形状（仅提供圆形/圆角矩形两档） |

## 2.6 全局「不支持场景」清单与替代路径

| 不支持场景 | 替代路径 |
|---|---|
| WebView / HTML 渲染 / Markdown 富文本预览 | v1 组件集不含；需该能力的积木暂不迁移（见第八章 wechat-mp 结论） |
| Canvas 自定义绘制、图表绘制 | 逻辑进程生成图片（PNG）经能力代理返回，用 `image` 展示；或使用 `progress` + `text` 组合的简化表达 |
| 拖拽（排序 / 跨区拖放 / 文件拖入） | 提供「上移 / 下移 / 选择目标」按钮，由逻辑进程变更顺序 |
| 富文本编辑、表格单元格编辑 | 使用 `textarea` + 纯文本约定；结构化编辑拆为多字段表单 |
| 多窗口 / 菜单栏 / 托盘 / 全局快捷键 | 不做，积木仅存在于主区域 |
| 自定义动画、转场、视差 | 渲染器统一提供动效，积木不可指定 |
| 直接读写系统剪贴板 / 通知 | 需 `ui.clipboard.write` / `notify` 权限（见第五章） |
| 本地生物识别、OCR、PDF 解析等系统框架能力 | 由底座能力代理（新增 `auth.biometric`、`ocr.recognize` 等，见第五、八章） |
| 任意网络请求（含 WebSocket 长连接） | 只读抓取走 `agent.web`；**写类请求**（显式 method/body，含 multipart 上传）须走受控网络写 `agent.web.write`（host 白名单 + 高危，见 §5.3.8）；长连接（WebSocket 等）不支持，需要长连接的积木暂不迁移 |

## 2.7 静态约束与校验

| 约束项 | 建议上限 | 超限行为 |
|---|---|---|
| 单帧节点数 | 2000 | 整帧拒绝，保留上一有效帧，回 `430x` 并提示积木 |
| 节点嵌套深度 | 16 | 同上 |
| 单帧 JSON 体积 | 512 KB | 同上 |
| 单节点文本长度 | 4000 字符 | 截断并回警告事件 |
| 图片单边像素 | 4096 | 拒绝该节点，渲染占位 |
| 事件频率 | 30 次/秒（可被 manifest 覆盖） | 超出丢弃并计一次违规（见第五章） |

**校验时机**：所有校验在渲染前完成；校验失败**不改变已渲染界面**（保持上一有效帧），并向逻辑进程回错误事件，向用户显示积木内嵌错误提示。UI 文档的离线校验器与运行时校验器共用同一份规则表，供市场发布前预检。

## 2.8 更新策略

| 策略 | 适用阶段 | 说明 |
|---|---|---|
| 全量快照 | Phase A 起可用 | `ui/update` 携带完整 `root`；实现简单，适合中小界面 |
| 路径 patch | Phase B 起支持 | `{"op":"set\|insert\|remove","path":"root.children[2].props.value", ...}`；大列表增量更新用 |
| 状态局部更新 | Phase B 起支持 | 仅更新 `state_snapshot` 并复用上一帧结构（插值重求值），适合纯文本/数值刷新 |

三种策略均以 `state_version` 单调递增为前提；渲染器对乱序帧直接丢弃并记日志。

### 2.8.1 三模式实现细则（B2，2026-10-03 落地）

实现：`app/Sources/BrickRenderer/UIPatch.swift` + `BrickRendererStore.swift`（底座侧）、`sdk/python/brick_sdk.py`（逻辑进程侧）。
线格式见 §4.5；本节只补「渲染器如何判定合法」的细则。

**路径文法**：`path := "root" ( "." key | "[" index "]" )*`；`root` 单独出现表示根节点本身。
`key` 限 `[A-Za-z_][A-Za-z0-9_-]*`，`index` 为非负整数，路径一律从 `root` 起算。

| 操作 | 语义 | 拒绝条件（整帧 `4303`） |
|---|---|---|
| `set` | 替换**已存在**的目标（含 `root` 整树替换） | 目标不存在（键写错不得静默新建） |
| `insert` | 末段 `[i]` → 数组插入（`0...count`，`count` 为追加）；末段 `.key` → 新建对象键 | 键已存在、下标越界、路径为 `root` 本身 |
| `remove` | 删除数组元素或对象键 | 目标不存在、路径为 `root` 本身 |

- **patch 与 full 同一套校验标准**：patch 先应用到上一有效帧的 JSON 树，结果整体走严格解码 + 全量校验
  （节点数 / 深度 / 体积 / 键白名单 / id 唯一）。任一失败 → **整帧拒绝，保留上一有效帧**，回 `ui/error`。
- **操作数上限** `maxPatchOps`（超限 `4304`）；`patch` 可为单个操作对象（等价单元素数组），空数组 → `4303`。
- **基底约束**：`patch` / `state` 帧都必须有上一有效帧（首帧必须 `mode=full`），否则 `4303`；
  `patch` 不得携带 `root`，`state` 不得携带 `root` / `patch`（整树替换请发 `full`）。
- **state 帧**：仅换 `state_snapshot` 并复用上一帧结构（插值重求值），体积按快照计；
  缺 `state_snapshot` → `4303`。
- **SDK 侧默认行为**（`push(mode="auto")`）：`render(state)` 与上一帧一致 → 自动发 `state`；
  否则发 `full`。`push_patch(ops)` 发 `patch`，无基底时降级为 `full`；事件处理器内已自发帧时，
  事件末尾不再兜底补帧（避免重复帧）。
- **SDK 不校验 ops 与 `render(state)` 等价**（只做转发与基底记录）：两者不一致时，底座以
  「patch 结果」为准，逻辑进程需自行保证一致，否则后续 `state` 帧插值会基于旧结构。
# 三、积木 manifest v2 字段定义

## 3.1 设计原则

1. **显式声明、默认拒绝**：权限、配额、入口一律显式写出，未声明即不可用。
2. **可静态审计**：安装器与发布闸门仅凭包内容即可判定合法性，不需要运行积木。
3. **向后兼容**：v1 独立 .app 积木在过渡期继续可装可跑，v2 为新增 schema，不修改 v1 语义。
4. **单文件自描述**：`manifest.json` 是积木的唯一入口声明，禁止多处配置互相覆盖。

## 3.2 v2 完整示例

```json
{
  "schema": "brick-app/v2",
  "brick_id": "com.shadeling.vault",
  "name": "vault",
  "title": "保险箱",
  "version": "2.0.0",
  "summary": "本地加密资产保管与检索",
  "author": "shadeling",
  "kind": "product",
  "nav": {
    "view_id": "vault",
    "title": "保险箱",
    "icon": "lock.shield",
    "order": 100
  },
  "ui": {
    "engine": "shadeling-ui/1",
    "entry": "ui/main.json",
    "theme": "brick-light"
  },
  "logic": {
    "protocol": "jsonrpc-stdio/1",
    "entry": "logic/vault",
    "runtime": "executable",
    "args": [],
    "env": {}
  },
  "permissions": ["agent.chat", "ui.sheet", "ui.clipboard.write", "auth.biometric"],
  "quota": {
    "ui_events_per_sec": 30,
    "max_nodes": 2000,
    "storage_mb": 256,
    "rss_mb": 512
  },
  "legacy": {}
}
```

> 注：`logic` 段还须按 §3.3 登记完整性凭据（`sha256` 或 `signature` 二者至少其一），上例省略具体摘要值；`logic.env` 未列举键一律拒装，首批白名单为空集故示例取 `{}`。

## 3.3 字段表

### 元数据段

| 字段 | 类型 | 必填 | 默认 | 语义 | 校验规则 |
|---|---|---|---|---|---|
| `schema` | string | 是 | — | 固定 `brick-app/v2` | 不在白名单 → 安装器拒绝并提示「需升级底座」 |
| `brick_id` | string | 是 | — | 全局唯一标识（反域名） | `^[a-z0-9]+(\.[a-z0-9-]+)+$`，与已装积木冲突 → 拒绝 |
| `name` | string | 是 | — | 目录名与安装目录键 | `^[a-z0-9][a-z0-9-]{1,31}$` |
| `title` | string | 是 | — | 显示名（≤32 字） | 非空 |
| `version` | string | 是 | — | 语义化版本 | `^\d+\.\d+\.\d+$`，同 brick_id 需单调递增 |
| `summary` | string | 是 | — | 一句话说明（≤120 字） | 非空，用于市场与安装确认页 |
| `author` | string | 否 | `""` | 作者标识 | ≤64 字 |
| `kind` | string | 是 | — | `product` / `builtin` / `legacy-app` | 枚举外 → 拒绝 |

### 导航段 `nav`（替代旧 `views[]`）

| 字段 | 类型 | 必填 | 默认 | 语义 | 校验规则 |
|---|---|---|---|---|---|
| `view_id` | string | 是 | — | 主区域槽位标识 | `^[a-z][a-z0-9_]{1,31}$`，同底座内唯一 |
| `title` | string | 是 | — | 宿主外壳标题 | ≤32 字 |
| `icon` | string | 否 | `square.grid.2x2` | 图标名 | 必须在图标白名单内 |
| `order` | int | 否 | 100 | 工坊/入口排序 | 0~999 |

> v1 的 `views[]` 数组在 v2 中收敛为单一 `nav`：内嵌形态下每只积木在主区域只占一个槽位，多视图切换由积木内部用 `picker(mode=segment)` 或自绘导航实现。

### UI 入口段 `ui`

| 字段 | 类型 | 必填 | 默认 | 语义 | 校验规则 |
|---|---|---|---|---|---|
| `engine` | string | 是 | — | UI 引擎版本，固定 `shadeling-ui/1` | 不在支持列表 → 拒绝并提示升级 |
| `entry` | string | 是 | — | 首帧 UI 文档路径（包内相对） | 存在性校验；禁止绝对路径、`../`、符号链接逃逸 |
| `theme` | string | 否 | `brick-light` | 主题令牌集 | 枚举：`brick-light` / `brick-dark`（跟随系统时由底座裁决） |

### 逻辑入口段 `logic`

| 字段 | 类型 | 必填 | 默认 | 语义 | 校验规则 |
|---|---|---|---|---|---|
| `protocol` | string | 是 | — | 固定 `jsonrpc-stdio/1` | 枚举外 → 拒绝 |
| `entry` | string | 是 | — | 逻辑进程可执行文件（包内相对） | 存在 + 可执行位校验；禁止路径逃逸 |
| `runtime` | string | 否 | `executable` | `executable`（自带可执行）/ `python3`（底座内置解释器） | 枚举外 → 拒绝 |
| `args` | string[] | 否 | `[]` | 启动参数 | 单参数 ≤256 字符，禁止 shell 元字符 |
| `env` | object | 否 | `{}` | 额外环境变量 | **显式正列举白名单**（`BrickInstallGate.allowedLogicEnvKeys`，首批为空集 → `logic.env` 必须为空对象）：未列举键**安装期拒装**、运行期不注入；`SHADELING_*` 仍为底座保留（manifest 不得声明，底座自身注入语义不变）；键名格式与值（路径分隔符 / 凭据样式串 / 非字符串）纵深校验保留；**放行具体键须先做「底座 ↔ 契约 §3.3」同步登记，禁止按前缀或通配放行** |
| `sha256` | string | 条件必填 | — | `logic.entry` 的完整性凭据（哈希登记） | 64 位十六进制；安装期与包内 `logic.entry` 实际字节比对，不一致 → 拒装。与 `signature` **二者至少其一** |
| `signature` | string | 条件必填 | — | `logic.entry` 的完整性凭据（签名登记） | 须以 `shadeling-sig/v1:` 开头；**仅做格式校验，不做验签**。与 `sha256` **二者至少其一** |

> **`logic.entry` 完整性凭据口径（2026-10-06 owner 按建议拍板，取 C；原「2026-10-04 补充判定」转正）**
> 安装器与发布闸门（§3.6 / §7.4 C4）要求 `logic.entry` 在 manifest 中**登记哈希或签名**，正式口径如下：
> - `logic.sha256`：64 位十六进制摘要，**推荐**（安装期与包内实际文件比对，不一致则拒绝安装）；
> - `logic.signature`：以 `shadeling-sig/v1:` 为前缀的签名字符串，**仅做格式校验，不做验签**。
> 二者**至少其一存在且格式合法**即通过；二者皆缺 → 拒装并按 §3.6-4 文案报错。**本轮不做真实验签**（真实验签留到对外分发，随付费开发者账号 + 公证一并做）。两处判据同源：宿主 `BrickInstallGate.validateLogicEntryIntegrity` / `logicSHA256Pattern` / `logicSignaturePrefix` 与发布闸门 `verify_products.verify_logic_entry`（`SHA256_RE` / `SIGNATURE_PREFIX`）。（对应 Shadeling `specs/state-2026-10-03.md` §12.6-1 / §16）

### 权限段 `permissions`

沿用 `BrickPermission` 命名空间，v2 扩展为三类：

| 类别 | 取值 | 说明 |
|---|---|---|
| 桥权限 | `agent.chat` / `agent.web` / `agent.fs.read` / `agent.browser` / `agent.local` | 与 brick-agent-bridge v0 完全一致，高危为 `agent.browser` / `agent.local` |
| UI 侧权限（v2 新增） | `ui.sheet` / `ui.clipboard.write` / `ui.open_url` / `fs.pick` / `notify` / `auth.biometric` / `ocr.recognize` | 见第五章风险级别与标红规则 |
| 应用级声明 | `network` 等（v1 遗留） | v2 中 `network` 不再授予直连能力，仅作为「需要联网」的市场提示标记 |

**校验规则**：不在已知枚举内的权限名 → 安装器拒绝（不做静默忽略）；高危权限 → 安装确认页标红并需显式勾选。

### 配额段 `quota`

| 字段 | 类型 | 必填 | 默认 | 语义 |
|---|---|---|---|---|
| `ui_events_per_sec` | int | 否 | 30 | 事件频率上限（1~120） |
| `max_nodes` | int | 否 | 2000 | 单帧节点数上限（100~5000） |
| `storage_mb` | int | 否 | 128 | 私有数据目录配额（16~2048） |
| `rss_mb` | int | 否 | 512 | 逻辑进程内存软上限（128~2048） |

> 取值超出区间 → 安装器钳制到区间边界并记录警告，不拒绝安装。全局上限由底座裁决，manifest 只能收紧不能放宽（见第五章）。

### 兼容段 `legacy`

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `legacy.bundle` | string | 否 | 仅 `kind: "legacy-app"` 使用，指向 `.app` bundle 名；`kind: "product"` 携带该字段 → 校验失败 |

## 3.4 v1 → v2 字段对照

| v1 字段 | v2 处置 | 说明 |
|---|---|---|
| `schema: brick-app/v1` | 升级为 `brick-app/v2` | 新 schema 需底座支持；旧底座拒绝并提示升级 |
| `bundle` | 移入 `legacy.bundle`，仅 `kind: legacy-app` | 声明式积木不再有 bundle |
| `views[]` | 收敛为 `nav` | 多视图由积木内部切换 |
| `buttons[]`（旧入口按钮） | 移除 | 入口统一由 `nav` 声明，主区域内按钮由 UI 文档描述 |
| `content`（提示词注入文本） | 移除 | 声明式积木不注入提示词；如需主模型能力走 `agent.chat` |
| `files[]`（文件落位声明） | 由包内 `ui/`、`logic/` 目录结构替代 | 安装器按目录约定落位，不再逐文件声明 |
| `capabilities` / `dependencies` / `resources` / `risk_level` / `composition` | 由 `permissions` + `quota` + `logic` 替代 | 旧五字段语义并入新段，`risk_level` 由高危权限自动推导 |
| `permissions` | 保留并扩展 | 新增 UI 侧权限枚举 |

## 3.5 兼容矩阵

| manifest | 底座版本 | 安装 | 运行行为 |
|---|---|---|---|
| `brick-app/v1` + `bundle` | 兼容期（≥ 现网版本） | 允许 | 走 legacy 独立窗口路径（BrickScene 形态），市场标注「旧形态」 |
| `brick-app/v1` 无 `bundle` | 兼容期 | 允许 | 旧声明式五字段积木，维持现状（工坊入口 + 提示词降级） |
| `brick-app/v2` | ≥ 声明式渲染版本 | 允许 | 内嵌主区域 + 逻辑进程 |
| `brick-app/v2` | 旧底座 | 拒绝 | 安装器提示「该积木需要新版底座」并给出升级入口 |
| `brick-app/v2` 缺 `nav` / `ui` / `logic` 任一段 | ≥ 声明式渲染版本 | **拒绝** | 安装期硬卡点：按 §3.6-1 报错，文案区分「整段缺失 / 存在但不是对象」 |
| `brick-app/v1`（含未标 `schema` 的历史包） | 兼容期 | 允许 | **不强制** `nav` / `ui` / `logic` 三段，按本表上方 v1 两行走 legacy 路径 |
| `brick-app/v1` + `bundle` | 声明式渲染版本之后（退役期） | 拒绝新装 | 已装实例可继续运行，市场不再上架 |

> **三段硬卡点的适用范围（2026-10-06 owner 按建议拍板，取 A）**：`nav` / `ui` / `logic` 三段强制只作用于 `schema=brick-app/v2`；**v1（含未标 `schema` 的历史包）不强制三段**，兼容期内维持原有校验与运行路径。判据同源：宿主 `BrickInstallGate.requiredSections` / `validateRequiredSections` + 安装流程早检（先于字段级文案，避免被「缺 `nav.view_id`」淹没）与发布闸门 `verify_products.verify_required_sections`（`REQUIRED_SECTIONS`）。

## 3.6 安装器校验清单（v2 新增项）

1. **（早检）`brick-app/v2` 强制三段**：`nav` / `ui` / `logic` 任一段缺失（含「段存在但不是对象」）→ **安装期硬卡点拒装**，报错文案须区分两种情况，参考文案：`缺少 {nav|ui|logic} 段（整段缺失|存在但不是对象）：brick-app/v2 强制 nav / ui / logic 三段齐备，缺一不可（契约 §3.3）`。本项须在字段级文案之前执行（否则会被「缺 `nav.view_id`」淹没）；**v1（含未标 `schema` 的历史包）不适用本项**（§3.5）。
2. `schema` / `kind` / `engine` / `protocol` / `runtime` 枚举合法性。
3. `brick_id` 唯一性与 `version` 单调性（已装同 id 版本比较）。
4. `ui.entry` 与 `logic.entry` 存在性、可执行位（`logic`）、路径逃逸（`..`、绝对路径、符号链接解析后越界）检查；**`logic.entry` 完整性凭据**：`logic.sha256`（64 位十六进制，与包内入口实际字节比对一致）或 `logic.signature`（前缀 `shadeling-sig/v1:`，仅格式校验）**二者至少其一**，皆缺或格式非法 → 拒装（口径见 §3.3）。
5. `logic.env` 键白名单校验：仅放行 `BrickInstallGate.allowedLogicEnvKeys` 显式正列举的键（首批为空集 → `logic.env` 必须为空对象），未列举键安装期拒装、运行期不注入；`SHADELING_*` 为底座保留、manifest 不得声明。
6. 权限枚举合法性（`BrickPermission.isKnown`）+ 高危标红渲染 + 未勾选高危权限则拒绝授予（不影响安装，运行时该能力调用被拒）。
7. `quota` 区间钳制与记录；**存在钳制项时必弹安装确认页**并逐条展示被钳制项（越界只收紧、不拒装）。
8. **UI 文档离线预校验**：按第二章规则表校验 `ui.entry` 及引用文档（节点数、深度、类型与属性白名单、图片引用是否包内），失败则拒绝安装并给出具体节点路径。
9. 发布闸门扩展（`verify_products.py`）：在现有「zip 完整性 / sha256 / manifest 一致性」三项之外，新增四项检查——① `brick-app/v2` 三段（`nav` / `ui` / `logic`）齐备；② `ui.entry` 存在且在包内可解析、无裸弹层调用（必须经 `overlay` 节点）；③ `logic.entry` 已登记哈希或签名（仅格式与一致性校验）；④ `logic.env` 键白名单。`ZIP_MANIFEST_FIELDS` 含 `nav` / `ui` / `logic`；v1（bundle 形态）在兼容期不适用本组检查。发布闸门与宿主安装器**判据同源**（同一份 §3.3 / §3.5 / §3.6 口径）。

## 3.7 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| B1 | v2 用 `ui` + `logic` 双入口替代 `bundle` | 无窗口形态下 bundle 无语义，双入口直接对应三层架构 |
| B2 | `views[]` 收敛为单一 `nav` | 主区域单槽位，多视图属积木内部实现 |
| B3 | 未知权限名直接拒绝安装，不静默忽略 | 避免「声明了却没生效」的安全误判 |
| B4 | `quota` 只能收紧不能放宽全局上限 | 防止恶意 manifest 自我提权 |
| B5 | UI 文档在安装期离线预校验 | 把渲染期错误前移到发布闸门，降低线上崩溃面 |
# 四、底座与逻辑进程协议（JSON-RPC over stdio）

## 4.1 传输层选择

| 候选 | 优势 | 否决理由 |
|---|---|---|
| 本地 TCP socket（既有 `runtime/ipc.py` 形态：`127.0.0.1:port` + `protocol_version`） | 已有实现，可复用 | 需分配端口、暴露本机网络面、需额外鉴权；进程崩溃与连接断开非同一事件，需额外心跳判定 |
| Unix domain socket | 无网络面 | 仍需路径与权限管理，崩溃检测仍需额外机制 |
| **stdin/stdout（采用）** | 进程父子关系天然绑定鉴权；stdout EOF 即崩溃信号；无需端口与额外鉴权面；可阻塞式背压 | 需自定义帧协议（见 §4.2）；不便于跨机调试 |

**结论**：底座以子进程方式拉起逻辑进程，二者在 stdin/stdout 上以 JSON-RPC 通信；stderr 作为日志直通通道，不参与协议。

## 4.2 帧格式

采用 LSP 风格长度前缀帧，避免 JSON 内容中的换行与转义问题：

```
Content-Length: <字节数>\r\n
\r\n
<UTF-8 JSON 正文>
```

| 规则 | 约定 |
|---|---|
| 编码 | UTF-8，无 BOM |
| 帧头 | `Content-Length: N\r\n\r\n`（N 为正文字节数，不含帧头） |
| 单帧上限 | 1 MB（超限按 `4305` 处理） |
| 换行 | 帧头使用 `\r\n`；正文内允许任意换行 |
| 日志 | 一律写 stderr（单行文本），禁止混入 stdout |

## 4.3 握手与版本协商

**底座 → 逻辑进程 `initialize`（request，id `h1`）**

```json
{
  "jsonrpc": "2.0",
  "id": "h1",
  "method": "initialize",
  "params": {
    "protocol_version": "jsonrpc-stdio/1",
    "ui_schema": "shadeling-ui/1",
    "brick_id": "com.shadeling.vault",
    "session_id": "s-8f3a...",
    "brick_version": "2.0.0",
    "granted_permissions": ["agent.chat", "ui.sheet"],
    "declared_permissions": ["agent.chat", "ui.sheet", "auth.biometric"],
    "quota": { "ui_events_per_sec": 30, "max_nodes": 2000, "storage_mb": 256, "rss_mb": 512 },
    "theme": { "mode": "light", "tokens_version": "1" },
    "locale": "zh-CN",
    "viewport": { "width": 688, "height": 620, "scale": 2.0 },
    "private_dir": "/Users/<user>/Library/Application Support/Shadeling/bricks/com.shadeling.vault/data"
  }
}
```

**逻辑进程 → 底座（response）**

```json
{
  "jsonrpc": "2.0",
  "id": "h1",
  "result": {
    "protocol_version": "jsonrpc-stdio/1",
    "ui_schema": "shadeling-ui/1",
    "ready": true
  }
}
```

**握手后**：底座发 `initialized` 通知，逻辑进程收到后方可推送首帧 `ui/update`。

| 不兼容情形 | 底座行为 |
|---|---|
| `protocol_version` 不匹配 | 回 `4301`，终止逻辑进程，槽位显示「积木与底座版本不兼容，请更新积木」 |
| `ui_schema` 不支持 | 回 `4302`，同上 |
| 握手超时（10s 无响应） | 判定启动失败，按 `4308` 呈现崩溃态 |
| `granted_permissions` 与 `declared_permissions` 不一致 | 正常：未授予项调用时回 `4309`，不影响启动 |

## 4.4 方法总表

### 下行：底座 → 逻辑进程

| 方法 | 类型 | 说明 |
|---|---|---|
| `initialize` | request | 握手（见 §4.3） |
| `initialized` | notification | 握手完成，允许推送首帧 |
| `event/dispatch` | notification | 用户事件回传：`{node_id, event, payload, ui_state, state_version}` |
| `ui/resize` | notification | 主区域尺寸/缩放变化：`{width, height, scale}` |
| `ui/theme` | notification | 主题或外观切换：`{mode, tokens_version}` |
| `ui/focus` | notification | 槽位激活/失活：`{focused: true|false}`（失焦后可降频刷新） |
| `ui/backpressure` | notification | 渲染压力提示：`{pending_frames}`，建议积木降频 |
| `lifecycle/suspend` | request | 离开槽位（切工坊/详情页），要求保存状态并停止刷新 |
| `lifecycle/resume` | request | 回到槽位，要求恢复并推送最新帧 |
| `lifecycle/shutdown` | request | 卸载/退出/退役，要求限时退出（默认 2s） |
| `ping` | notification | 心跳（每 5s） |

### 上行：逻辑进程 → 底座

| 方法 | 类型 | 说明 |
|---|---|---|
| `ui/update` | notification | UI 快照：`{state_version, mode: "full"|"patch"|"state", root?/patch?/state_snapshot?}` |
| `capability/call` | request | 能力调用：`{method, params}`，`method` 必须在白名单内 |
| `overlay/request` | notification | 即时弹层/横幅：`{kind: "banner"|"toast"|"dialog", ...}`（声明式弹层优先用 UI 文档内 `overlay` 节点） |
| `ui/error` | notification | 积木自检异常：`{code, message, node_id?}` |
| `log` | notification | 分级日志：`{level: "debug"|"info"|"warn"|"error", message}` |
| `pong` | notification | 心跳响应 |
| `shutdown/ack` | response | `lifecycle/shutdown` 的响应 |

### id 命名空间约定

| 发起方 | id 形态 | 示例 |
|---|---|---|
| 底座 | `h` + 递增整数 | `h1`、`h2` |
| 逻辑进程 | 递增整数 | `1`、`2` |

双向 id 空间互不冲突；请求方负责在超时（默认 15s）后判定失败。

## 4.5 关键消息示例

**事件回传（下行）**

```json
{
  "jsonrpc": "2.0",
  "method": "event/dispatch",
  "params": {
    "node_id": "btn_save",
    "event": "tap",
    "payload": {},
    "ui_state": { "focused_id": "field_title", "scroll_y": 0, "draft_text": "草稿标题" },
    "state_version": 41
  }
}
```

**UI 快照（上行，全量）**

```json
{
  "jsonrpc": "2.0",
  "method": "ui/update",
  "params": {
    "state_version": 42,
    "mode": "full",
    "root": { "type": "container", "id": "root", "props": { "direction": "vertical" }, "children": [] },
    "state_snapshot": { "items": 12, "loading": false }
  }
}
```

**UI 快照（上行，路径 patch / B2）**

```json
{
  "jsonrpc": "2.0",
  "method": "ui/update",
  "params": {
    "state_version": 43,
    "mode": "patch",
    "patch": [
      { "op": "set", "path": "root.children[1].props.value", "value": "已保存" },
      { "op": "insert", "path": "root.children[2].children[3]",
        "value": { "type": "text", "id": "row_4", "props": { "value": "第 4 条" } } },
      { "op": "remove", "path": "root.children[2].children[0]" }
    ],
    "state_snapshot": { "items": 12, "loading": false }
  }
}
```

**UI 快照（上行，状态局部 / B2）**

```json
{
  "jsonrpc": "2.0",
  "method": "ui/update",
  "params": {
    "state_version": 44,
    "mode": "state",
    "state_snapshot": { "items": 13, "loading": false }
  }
}
```

> `state` 帧只换状态，结构沿用上一有效帧；插值节点按新状态重求值。判据与拒绝条件见 §2.8.1。

**能力调用（上行 request）**

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "capability/call",
  "params": { "method": "agent.web", "params": { "query": "某主题", "limit": 5 } }
}
```

**能力结果（下行 response）**

```json
{ "jsonrpc": "2.0", "id": 7, "result": { "items": [] } }
```

## 4.6 生命周期时序

| 阶段 | 时序 |
|---|---|
| 启动 | 底座 spawn（cwd = 私有目录，env 注入 `SHADELING_BRICK_ID` / `SHADELING_SESSION_ID` / `SHADELING_LOG_LEVEL`）→ `initialize` → 应答 → `initialized` → 首帧 `ui/update` → 渲染 |
| 交互 | 渲染器 `event/dispatch` → 逻辑进程更新 state → `ui/update` → 渲染器应用新帧 |
| 能力调用 | 逻辑进程 `capability/call` → 闸门（声明/授予/配额三重校验）→ 既有 IPC handler → response → 逻辑进程更新 state → `ui/update` |
| 槽位切换 | 切走：`lifecycle/suspend`（要求 1s 内应答）→ 停止刷新；切回：`lifecycle/resume` → 推送最新帧 |
| 尺寸变化 | 主区域宽度变化（如右栏展开/收起）→ `ui/resize` → 逻辑进程按新 viewport 重排（栅格列数等） |
| 退出 | 用户关闭积木/退出底座 → `lifecycle/shutdown` → 2s 未应答 → `SIGTERM` → 1s → `SIGKILL` |

## 4.7 错误码

既有 `429x` 段继续承载桥权限与主模型配额；本文新增 `430x` 段承载协议与渲染错误：

| 码 | 名称 | 触发条件 | 底座行为 |
|---|---|---|---|
| 4301 | `PROTOCOL_VERSION_MISMATCH` | 握手 `protocol_version` 不匹配 | 终止进程 + 槽位错误态 |
| 4302 | `UI_SCHEMA_UNSUPPORTED` | `ui_schema` / `engine` 不支持 | 终止进程 + 槽位错误态 |
| 4303 | `UI_DOC_INVALID` | UI 文档校验失败（含节点路径） | 保留上一有效帧 + 回 `ui/error` |
| 4304 | `UI_LIMIT_EXCEEDED` | 超节点数 / 深度 / 体积限额 | 整帧拒绝 + 计一次违规 |
| 4305 | `FRAME_DECODE_ERROR` | 帧头或 JSON 非法 | 记日志；连续 3 次 → 按 `4308` 终止 |
| 4306 | `EVENT_RATE_LIMITED` | 事件超频 | 丢弃 + 横幅降级提示 |
| 4307 | `LOGIC_TIMEOUT` | 请求超时（默认 15s；能力调用沿用既有 25s） | 回超时错误，不终止进程 |
| 4308 | `LOGIC_CRASHED` | 进程退出 / 心跳超时 / 启动失败 | 槽位崩溃态 + 可重启 |
| 4309 | `CAPABILITY_DENIED` | 权限未声明或未授予 | 回错误 + 违规计数 |
| 4310 | `QUOTA_EXCEEDED` | 配额耗尽（明细沿用 429x 口径） | 回错误 + 提示恢复条件 |

## 4.8 崩溃检测与恢复

**检测手段**

| 手段 | 判定 |
|---|---|
| stdout EOF | 立即判定进程已退出 |
| 进程退出码 | 非 0 记录退出码与最后 50 行 stderr 摘要 |
| 心跳 | 底座每 5s 发 `ping`，10s 内无 `pong` 记一次超时；连续 2 次判定挂死 |

**恢复流程**

1. 判定挂死 → `SIGTERM` → 1s 未退出 → `SIGKILL`。
2. 槽位保留：导航位置、`brick_id`、用户当前所在页面不变；界面切换为崩溃态（错误摘要 + 「重启积木」+「返回工坊」）。
3. 用户点「重启」或自动重启：同 `brick_id` 重新 spawn，走完整握手；积木自行从私有目录恢复业务状态（底座不代管业务状态，仅传 `session_id`）。
4. 渲染器以新首帧整体替换崩溃态。

**崩溃循环保护**：60s 内重启 ≥ 3 次 → 停止自动重启，提示用户「该积木反复崩溃，已暂停」，并记入市场质量统计。

## 4.9 背压与流控

| 场景 | 规则 |
|---|---|
| 连续 `ui/update` | 渲染器按 `state_version` 合并，只渲染最新帧；丢弃的中间帧不回执 |
| 渲染耗时 > 100ms | 底座发 `ui/backpressure`（`pending_frames`），积木应降频（建议 ≥ 100ms 合并一次） |
| 逻辑进程写入 stdout | 阻塞式写；需处理 EPIPE（底座已退出时立即自行退出） |
| 能力调用排队 | 沿用既有 429x 并发口径（默认并发 1，超出回 429 语义错误） |

## 4.10 调试与可观测性

- **stderr 直通**：底座按 `[brick:<brick_id>]` 前缀写入日志；仅 debug 构建落盘，Release 保留最近 200 行环形缓冲供崩溃上报。
- **协议帧调试**：环境变量 `SHADELING_BRICK_DEBUG=1` 时，底座将协议帧（脱敏：移除 token 与凭据类字段）写入 stderr。
- **质量统计**：崩溃次数、`430x` 错误分布、平均帧大小、平均渲染耗时按 `brick_id` 聚合，供市场页展示「稳定性」指标。

## 4.11 与既有 IPC 的关系

| 维度 | 既有 IPC（`runtime/ipc.py`，TCP socket） | 新通道（stdio） |
|---|---|---|
| 承载对象 | 底座 ↔ 主模型 / 连接器 / 工具 | 底座 ↔ 积木逻辑进程 |
| 传输 | `127.0.0.1:port`，`protocol_version: 1.1` | stdin/stdout，`Content-Length` 帧 |
| 鉴权 | 桥 token（`SHADELING_BRIDGE_ENDPOINT` + `SHADELING_BRIDGE_TOKEN` 注入） | 进程父子关系；`initialize` 携带 `session_id` 做会话绑定 |
| 能力落点 | handler 注册表（`brick_*` 等） | 闸门校验通过后复用**同一** handler 注册表 |
| 变更要求 | 无需改动既有传输与鉴权 | 新增 `430x` 错误码段与积木侧协议实现 |

**结论**：新通道不替换既有 IPC，而是把积木侧通信从「应用级 TCP + 注入 token」收敛为「stdio + 闸门代理」，既有的工具白名单、权限枚举与配额口径保持不变。

## 4.12 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| C1 | 采用 stdio + 长度前缀帧 | 生命周期与鉴权天然绑定，崩溃检测简单，无网络面 |
| C2 | 双向 JSON-RPC，id 命名空间分侧 | 生命周期请求由底座发起、能力请求由积木发起，需双向请求能力 |
| C3 | 能力调用复用既有 handler 注册表 | 避免两套能力实现与两套配额口径 |
| C4 | 崩溃后保槽位、可原地重启、循环保护 | 内嵌形态下崩溃不得影响底座；反复崩溃需止损 |
| C5 | 新增 `430x` 段而不改动 `429x` | 既有文档与实现基线不动，新增段独立演进 |
# 五、权限与配额模型

## 5.1 三层权限模型

```
① 声明（manifest.permissions）   →  ② 授予（安装确认 + 设置页）  →  ③ 校验（运行时闸门）
   未声明 = 不存在该能力            未勾选 = 不授予                 每次调用逐项复核
```

| 环节 | 执行者 | 规则 |
|---|---|---|
| 声明 | 积木作者 | 权限名必须在已知枚举内；未知权限名 → 安装器拒绝安装（不静默忽略） |
| 授予 | 用户 | 安装确认页逐项展示（含用途说明）；低危默认勾选、中危默认不勾选、高危标红且需二次确认；设置页可随时撤销 |
| 校验 | 底座闸门 | 每次 `capability/call` 依次校验「已声明 → 已授予 → 未超配额」，任一失败回 `4309` / `4310` |

**默认拒绝**：manifest 未声明的能力，调用一律失败并计违规；不提供「首次调用自动弹窗授权」的隐式提权路径。

## 5.2 权限清单与风险级别

### 桥权限（沿用 brick-agent-bridge v0 枚举，不变）

| 权限 | 级别 | 用户可见文案 | 安装页标红 |
|---|---|---|---|
| `agent.chat` | 中 | 调用主模型对话（无工具） | 否 |
| `agent.web` | 中 | 联网检索（搜索 + 只读抓取） | 否 |
| `agent.fs.read` | 中 | 读取本地文件（路径受底座沙箱约束） | 否 |
| `agent.browser` | **高** | 操作浏览器（复用已登录态） | **是** |
| `agent.local` | **高** | 操作本机界面（模拟键鼠） | **是** |
| `agent.web.write` | **高** | 受控网络写：仅向 host 白名单发 `GET`/`POST`，显式 method/body（含受控 multipart） | **是** |

> `agent.web.write` 为 2026-10-09 评审新增（即原 §8.4 暂称的 `agent.web.upload`），是 `agent.web` 只读抓取的**写入侧独立权限**，不与只读权限合并授予；最小授权面与逐能力 I/O 契约见 §5.3.8。

### UI 侧权限（v2 新增）

| 权限 | 级别 | 语义 | 安装页表现 | 备注 |
|---|---|---|---|---|
| `ui.sheet` | 低 | 使用弹层（sheet / dialog / banner / toast） | 默认勾选 | 若渲染器对所有积木默认开放弹层，则该项可降级为「提示项」而非权限项，见 §5.6 待决策 |
| `ui.clipboard.write` | 低 | 写系统剪贴板（写入内容在事件日志中留痕） | 默认勾选 | 仅写，不提供读取 |
| `notify` | 低 | 发送系统通知 | 默认勾选 | 通知内容需含积木名 |
| `ui.open_url` | 中 | 用系统默认浏览器打开外链 | 默认不勾选，提示「将离开本应用」 | 仅允许 `https` 链接 |
| `fs.pick` | 中 | 弹出系统文件选择器，读取用户主动选中的文件 | 默认不勾选 | 仅返回所选文件的受控句柄，不授予目录遍历 |
| `auth.biometric` | 中 | 调用本地生物识别（Touch ID）做二次验证 | 默认不勾选 | 用于敏感数据解锁场景（见第八章 vault） |
| `ocr.recognize` | 中 | 本地 OCR（图片 / PDF → 文本） | 默认不勾选 | 底座代理系统 Vision/PDFKit 能力 |

### 风险级别判定规则

| 级别 | 判定标准 | 安装页与运行时行为 |
|---|---|---|
| 低 | 不触及用户数据、不离开应用、可由用户直接感知结果 | 默认勾选；调用不弹二次确认 |
| 中 | 触及用户数据或离开应用边界，但作用范围受用户主动操作限定 | 默认不勾选；首次调用弹一次性确认 |
| 高 | 可代替用户操作其他应用或本机界面，或可读取任意用户文件 | **标红 + 默认不勾选 + 勾选后二次确认**；首次调用仍需一次性确认 |

## 5.3 运行时校验细节

1. **调用链**：`capability/call` → 查 `granted_permissions` → 查配额 → 记审计日志（时间 / brick_id / 方法 / 参数摘要，参数脱敏）→ 转既有 handler。
2. **未声明调用**：直接拒绝并计违规；同一积木累计 3 次违规 → 中断当前会话并在槽位提示「该积木请求了未声明的能力」，同时记入市场质量统计。
3. **高危权限的二次确认**：已授予的高危权限在首次实际调用时，仍需用户一次性确认（可勾选「本会话内不再询问」）；该确认不影响设置页的长期授权状态。
4. **撤销即时生效**：用户在设置页撤销权限后，下一次调用即返回 `4309`；不中断已完成的调用。
5. **审计留痕**：能力调用记录写入底座审计日志（保留 30 天，可在设置页按积木查看）。

### 5.3.6 能力调用回执信封与逐能力 I/O 契约

2026-10-08（Phase D3）落地。`capability/call` 的**成功应答**统一为如下信封：
积木侧业务返回值一律位于 `data`，不得在顶层平铺（顶层键是裁决元信息，由宿主填充）。

| 字段 | 类型 | 语义 |
|---|---|---|
| `allowed` | bool | 闸门是否放行；未放行走错误应答（`4309` 等），不出现本信封 |
| `capability` | string | 能力名回显，便于积木复用一个回调分发 |
| `level` | string | 风险级别（低 / 中 / 高） |
| `forward` | string | 宿主转发目标（`host` = 宿主 handler） |
| `data` | object | **业务返回值**，逐能力定义见下表 |
| `audit_seq` | int | 审计序号（自增） |
| `audit_persisted` | bool | 审计是否成功落盘 |
| `notice` | string | 越权中断等场景的槽位提示（可选） |

**逐能力 I/O（首批三项）**

| 能力 | 请求 `params` | 回执 `data` | 失败 / 边界语义 |
|---|---|---|---|
| `fs.pick` | `kinds: ["image" \| "pdf" \| "text"]`（可选，未列举或不可识别项即不限类型）<br>`files` / `directories` / `multiple`（可选，bool） | `{"cancelled": false, "paths": ["/绝对路径", ...]}` | 用户取消 → `{"cancelled": true, "paths": []}`，**非错误**，积木须静默回空闲、不得写错误态 |
| `auth.biometric` | `reason: string`（可选，展示给用户的说明） | `{"granted": true, "success": true}` | `{"granted": false, "success": false, "error": "原因"}`，**非错误应答**；积木不得解锁任何敏感字段 |
| `ocr.recognize` | `path: string`（绝对路径，须位于用户主目录内） | `{"text": string, "chars": int}` | 路径越界 / 文件不存在 / 解析失败 → 错误应答 + 对应错误码（不静默成功） |

**积木侧实现约束（红线）**

1. 业务键必须从 `data` 解包读取；兼容期允许顶层平铺形状（仅离线自测与早期宿主），但**不得以顶层键为准**。
2. `auth.biometric` 的裁决键是 `granted`，`success` 仅为兼容别名；**键缺失一律视为未通过**（安全默认）。历史实现「缺失取 True」按本契约纠正，回归项 P9.1~P9.3 常驻。
3. `fs.pick` 的取消是正常路径，不记错误、不弹失败提示。
4. `granted: false` 时必须给出可读原因（优先宿主 `error` 文案，其次本地兜底文案），且**不得部分解锁**。

### 5.3.7 数据落盘与私有目录口径（D4，2026-10-08 落地）

**落盘位置推导链**（逻辑进程与旧 Swift `VaultPaths.vaultDir` 同源，向后兼容）：

| 优先级 | 条件 | 库位置 | scope |
|---|---|---|---|
| 1 | 显式注入 `SHADELING_HOME` | `$SHADELING_HOME/vault/vault.db` | `home`（自测 / CI） |
| 2 | 宿主注入 `SHADELING_BRICK_PRIVATE_DIR`（= `bricks/<brick_id>/data`，§6.2） | `$SHADELING_BRICK_PRIVATE_DIR/vault.db` | `private`（正式运行） |
| 3 | 两路都缺席 | `~/Library/Application Support/Shadeling/vault`（存在时）→ `~/.shadeling/vault` | `legacy` |

**首次切换的旧库接管**：

1. 私有目录已有 `vault.db` → 直接使用（幂等，不重复接管）。
2. 私有目录无库且旧全局库存在 → 复制到私有目录，**逐字节 sha256 核对**一致才启用（`os.replace` 原子落位）；
   **旧库原文件一律保留**（可后悔），`.vault_key`（若存在）同法复制并置 0600。
3. 核对失败或 IO 异常 → **回退旧目录**（宁可用旧库也不丢数据），stderr 明示原因，不删除任何文件。

**卸载重装不丢**：安装目录 `Bricks/<安装名>`（宿主 `BrickPaths.installedProductRoot`）与私有目录
`bricks/<brick_id>/data` 分离；`AppModel.uninstallBrick` 只移除安装目录，私有库保留，重装后同 `brick_id`
读到同一份数据（回归项 P10.1~P10.8 常驻）。安装名与 `brick_id` 必须保持不同（现有 vault = 安装名
`vault` / `brick_id` `com.shadeling.brick.vault`），避免 macOS 大小写不敏感文件系统下 `bricks/` 与
`Bricks/` 同目录带来的边界歧义。

**校验和口径**：迁移 / 重装验收用两层——① 文件级 sha256（接管逐字节核对）；② 行级内容摘要
（`SELECT id,type,title,payload ORDER BY created_at,id` 的 sha256）。两者跨重装均须一致。

### 5.3.8 受控网络写（`agent.web.write`，2026-10-09 评审立项）

为 wechat-mp 等需要调用业务接口的积木提供**写入侧**网络能力。只读抓取仍走 `agent.web`（§2.6），
本能力只解决「POST/GET + body 载荷 / multipart 上传」这一类请求，以**最小授权面**为设计前提。
评审记录见 `specs/受控网络写能力评审-2026-10-09.md`。

**权限与风险**：级别 **高**；安装页**标红 + 默认不勾 + 勾选后二次确认**；首次实际调用仍需一次性确认
（可勾「本会话内不再询问」，§5.3-3）；未声明调用计违规（§5.3-2）。审计留痕见下。

**请求参数（`params`）**

| 字段 | 类型 | 约束 |
|---|---|---|
| `host` | string | **必填**，必须逐字符命中底座 host 白名单（当前白名单仅 `api.weixin.qq.com`）；不接受 IP 字面量、不接受前缀 / 后缀 / 通配匹配、不接受带端口或用户名 |
| `path` | string | **必填**，以 `/` 开头的绝对路径；禁止 `..`，禁止二次编码绕过 |
| `method` | string | **必填且显式**，枚举 `GET` / `POST`；其余方法（PUT / PATCH / DELETE 等）一律拒绝 |
| `query` | object | 可选，键值对（值仅 string / number / bool），由底座序列化 |
| `body` | object | 可选，**仅 JSON 对象**（`Content-Type: application/json`），由底座序列化；键名与嵌套深度沿用 §2.7 静态约束 |
| `multipart` | object | 可选，受控 multipart 上传（见下），与 `body` 互斥 |
| `timeout_ms` | int | 可选，缺省 15000，上限 30000 |

**multipart 受控口径**

| 项 | 约束 |
|---|---|
| 文件数 | 单次仅 **1 个**文件（`file`），其余为纯文本 `fields` |
| 文件来源 | 必须为 `fs.pick` 回执 `paths[]` 之一，或逻辑进程私有目录（§5.3.7）内文件；其余路径一律拒绝 |
| 大小 | ≤ 10 MB（`material/add_material` 上限）；超出拒绝 |
| 文件名 | 仅取 basename 并净化控制字符，由底座按白名单字符集重写 |
| 请求头 | 底座自行生成 `Content-Type: multipart/form-data; boundary=...`；**积木不得指定任意请求头** |

**凭据红线（本能力立项的前提条件）**

1. **凭据只留逻辑进程私有目录**（§5.3.7 `private` scope，文件权限 0600）；`appsecret`、`access_token`、
   会话票据一律按凭据处理，**不得写入日志、不得写入 UI 文档与 `state_snapshot`、不得作为能力参数上传给底座**。
2. **底座不做凭据注入、不做凭据托管**：桥只转发积木**显式给出**的请求要素，不读取、不缓存、不代填凭据；
   凭据的获取（`cgi-bin/token`）与续期同样由逻辑进程自行经本能力发起。
3. **日志与审计一律脱敏**：`query` / `body` 只记录键名与字节数、不记录取值；路径查询串中的
   `access_token` 等敏感键在留痕前遮蔽。
4. **违规即拒绝**：请求要素中出现凭据字段（`appsecret` / `secret` / `access_token` 等作为 `body` / `query` 键）
   → 直接拒绝并计一次违规；同一积木累计 3 次违规按 §5.3-2 中断会话。

**回执（`data`）**

| 字段 | 类型 | 语义 |
|---|---|---|
| `status` | int | HTTP 状态码 |
| `body` | string | 响应正文（UTF-8 文本）；非文本类型回 base64 并置 `encoding = "base64"` |
| `encoding` | string | `utf8`（缺省）/ `base64` |
| `bytes` | int | 响应字节数（截断前） |
| `truncated` | bool | 响应超过回执上限（1 MB）被截断时为 true；积木须显式提示，不得静默按完整响应处理 |
| `redirected` | bool | 恒为 false：**不跟随重定向**，遇 3xx 原样按 `status` 回给积木自行决策 |
| `audit_seq` | int | 审计序号（承接 §5.3.6 信封） |

**失败 / 边界语义**

| 场景 | 行为 |
|---|---|
| `host` 不在白名单 / 非 https / 带端口 | 拒绝（`4309`），**不发起任何网络连接**，计一次违规 |
| `method` 不在枚举 / `body` 与 `multipart` 同时出现 | 参数错误应答，不计违规 |
| 超时 / DNS 失败 / TLS 失败 | 错误应答（含可读原因），积木须回显为业务错误态 |
| 响应超限 | 截断 + `truncated: true` |
| 白名单扩展 | **必须走契约修订 + 安全评审**并在底座登记；不允许 manifest 自定义 host，不允许按前缀 / 通配放行 |

**积木侧实现约束**：① 网络失败必须映射为可读业务错误态；`upload_blocked` 一类降级横幅只适用于
「能力未授予 / 宿主 handler 未就绪」，不得把失败一律折叠成降级提示；② 上传类操作的进度与失败原因须对用户可见；
③ host 白名单、超时与各项上限以本契约为**唯一事实源**，逻辑进程不得自行放宽。

**协议兼容**：本能力**不新增错误码**，复用既有语义（`4309` 拒绝 / `4310` 超配额 / `4305` 帧错误）；
宿主 handler 与渲染器确认 UI 属底座侧实现项（见评审记录「落地清单」）。

## 5.4 配额体系

### 沿用既有口径（不重新定义）

| 配额 | 口径来源 | 取值 | 超限返回 |
|---|---|---|---|
| 主模型并发 | `ipc-schema-v0.md` 429x 段 | 1 | 429 语义错误 |
| 单积木日调用量 | `ipc-schema-v0.md` 429x 段 | 200 次/日 | 429 语义错误 |
| 主模型全局占用 | `ipc-schema-v0.md` 429x 段 | 主对话 30% 上限 | 429 语义错误 |

### 新增配额（本文建议值，待实测校准）

| 配额 | 默认值 | manifest 可覆盖 | 超限行为 |
|---|---|---|---|
| UI 事件频率 | 30 次/秒 | 可收紧（1~120） | 丢弃超额事件 + 横幅提示（`4306`） |
| 单帧节点数 | 2000 | 可收紧（100~5000） | 整帧拒绝，保留上一有效帧（`4304`） |
| 单帧 JSON 体积 | 512 KB | 不可覆盖 | 同上 |
| 逻辑进程内存（RSS） | 512 MB 软上限 | 可收紧（128~2048） | 达软上限发警告；达 1 GB 强制重启（`4308`） |
| 私有存储 | 128 MB | 可收紧（16~2048） | 写入失败并提示用户清理 |
| 重启频率 | 60s 内 3 次 | 不可覆盖 | 停止自动重启，槽位提示「已暂停」 |
| 协议帧大小 | 1 MB | 不可覆盖 | 按 `4305` 处理，连续 3 次终止进程 |
| 受控网络写请求体 | JSON ≤ 1 MB；multipart 文件 ≤ 10 MB | 可收紧 | 拒绝 + 提示用户（不发起请求） |
| 受控网络写日调用量 | 200 次/日（与「单积木日调用量」同一计数，不叠加） | 可收紧 | `4310` |

**收放原则**：manifest 只能收紧不能放宽全局上限；底座全局上限随版本可调，调低时对已装积木即时生效。

## 5.5 用户可见性与透明度

| 位置 | 内容 |
|---|---|
| 安装确认页 | 权限清单（含级别与用途文案）+ 高危标红 + 二次确认；展示 `quota` 声明值 |
| 积木详情页（设置内） | 已授予权限、可撤销；配额使用情况（今日调用量、存储占用、最近崩溃次数） |
| 槽位内提示 | 权限被拒（`4309`）、配额耗尽（`4310`）、超频降级（`4306`）、崩溃（`4308`）均以积木内嵌 banner 呈现，文案说明原因与恢复条件 |
| 审计查询 | 按积木查看最近 30 天能力调用记录（能力名 + 时间 + 结果；受控网络写额外记录 host / method / path 与响应码），参数与响应正文一律脱敏，不展示以防泄露 |

## 5.6 与既有实现的对齐

| 既有实现 | 处置 |
|---|---|
| `BrickPermission.known`（`agent.*` 五项） | 扩展为「桥权限 + UI 侧权限」两张表；`isBridge` 判定逻辑不变 |
| `BrickPermission.highRisk`（`agent.browser` / `agent.local`） | 保持；UI 侧权限的高危项（当前无）由新表统一声明 |
| `BrickPermission.label` | 补充 UI 侧权限的中文文案（见 §5.2） |
| 安装勾选与高危标红交互（`brick-market-v2.md`） | 复用；新增「级别 → 默认勾选状态」映射与高危二次确认弹窗 |
| `InstalledBrickManifest.declaredPermissions` / `grantedPermissions` | 字段语义不变；新增 `declaredPermissions` 与 `grantedPermissions` 差集用于 `4309` 判定 |
| `429x` 配额段 | 语义不变；本文新增配额在其之上叠加，不改变既有返回值 |

**已拍板（2026-09-26）**：`ui.sheet` **不设独立权限项，降级为「提示项」**——弹层由渲染器托管、对所有积木默认开放，无额外风险面，作为独立权限项只会增加安装页噪音。具体语义：`ui.sheet` 仍在合法权限枚举内（声明它不判未知、不拒装），仍按低危记账并默认授权，但安装确认页**不渲染独立开关**，仅以「提示项」列示。拍板来源：Shadeling `docs/TODO.md` L65（2026-09-26 拍板四项之一）。落地见 §7.4 C1。

## 5.7 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 三层模型（声明 / 授予 / 校验），无隐式提权 | 与既有桥权限模型一致，避免授权路径分裂 |
| D2 | 未知权限名拒绝安装 | 防止「声明未生效」的安全误判 |
| D3 | 高危权限「标红 + 默认不勾 + 二次确认 + 首调再确认」 | 与既有高危标红机制一致并加强 |
| D4 | 未声明能力调用计违规，3 次中断 | 抑制能力探测行为 |
| D5 | 新增配额取「可收紧不可放宽」 | 防止恶意 manifest 自我提权 |
| D6 | 配额与权限使用对用户可见、可撤销 | 透明度是内嵌形态下用户信任的前提 |
| D7 | 受控网络写独立立项（`agent.web.write`）：host 白名单 + 显式 method/body + 凭据仅留逻辑进程私有目录且不入日志不入桥 | 写操作不可逆、底座不得成为凭据托管方；最小授权面是 G4 重启提案的前置条件（2026-10-09 评审） |
# 六、与现有资产的关系及演进/退役方案

## 6.1 资产处置总表

| # | 资产 | 位置 | 处置 | 时机 | 改造量 |
|---|---|---|---|---|---|
| 1 | `BrickUIKit/Tokens.swift` | `app/packages/BrickUIKit/Sources/BrickUIKit/` | **100% 复用**：渲染器与 UI 文档的令牌引用共用同一令牌源，保证视觉一致 | Phase A | 无 |
| 2 | `BrickUIKit/Components.swift` | 同上 | **复用为主**：渲染器构建视图直接复用现有组件；组件集未覆盖的按第二章清单补齐 | Phase A~B | 中 |
| 3 | `BrickUIKit/BrickOverlays.swift` | 同上 | **复用**：作为 UI 文档 `overlay` 节点（sheet / dialog / banner）的实现层，契约语义不变 | Phase A | 小 |
| 4 | `BrickScene.swift`（980×680 窗口契约） | 同上 | **退役**：声明式形态无自建窗口；仅在 legacy 路径保留至 Phase E 删除 | Phase D→E | 删除 |
| 5 | `BrickLifecycleView`（关窗即退） | 同上 | **退役**：生命周期改由槽位管理（`lifecycle/suspend|resume|shutdown`） | Phase D→E | 删除 |
| 6 | `NativeBrickHostView.swift` | 底座主区域 | **演进**：升级为 `BrickHostView`——宿主外壳（标题 / 返回 / 关闭）+ 渲染器容器 + 崩溃态容器 | Phase A | 中 |
| 7 | `BrickViewRegistry.swift` | 底座 | **保留（限内置）**：继续服务底座内置积木（cabinet / agent_mail）；第三方积木一律走渲染器。**"不做运行时动态加载"红线不变** | 不变 | 无 |
| 8 | `AppModel.openProductBrick` | 底座 | **改造**：v2 积木改为「spawn 逻辑进程 + 主区域挂载渲染器」；v1 积木在兼容期继续走 `NSWorkspace` 打开 `.app` | Phase A | 大 |
| 9 | 桥 token 注入（`SHADELING_BRIDGE_ENDPOINT` / `SHADELING_BRIDGE_TOKEN`） | 底座 | **过渡保留**：仅 legacy 独立 .app 需要；v2 积木经 stdio + 闸门，不需要 token | Phase E 移除 | 中 |
| 10 | `runningBricks` 登记表 | 底座 | **语义改造**：由「运行中 GUI 进程」改为「逻辑进程句柄 + 槽位状态」；单实例由槽位天然保证 | Phase A | 小 |
| 11 | `createsNewApplicationInstance` 硬编码 | 底座 | **已执行（2026-10-09）**：legacy 产品拉起路径内的硬编码（`launchProductBrick` 中 `= false`）随路径整段删除；`main.swift` 的 `= true` 属 DMG 自换装（移入 /Applications 后拉起新副本）另有语义，**不在退役范围、保留** | Phase E | 小 |
| 12 | brick-agent-bridge v0 闸门（`runtime/brick_bridge.py` + `ipc.py`） | 底座 | **保留**：作为能力调用统一落点；扩展 UI 侧权限枚举与审计 | Phase A~C | 小 |
| 13 | 市场安装器 / `InstalledBrickManifest` | 底座 + 市场 | **演进**：支持 v2 schema、双入口校验、UI 文档离线预校验、级别化勾选 | Phase A~C | 中 |
| 14 | `scripts/verify_products.py` | 仓库 | **扩展**：新增「UI 入口存在且可解析」「无裸弹层调用」「logic 入口哈希登记」三项 | Phase C | 小 |
| 15 | 内置积木 `demo-studio` / `agent-mail` | 仓库 | **分流保留**：底座内部代码，不受第三方限制，继续走注册表原生路径 | 不变 | 无 |
| 16 | 《积木规范化模板规格 v0.1》 | `specs/` | **更新**：窗口契约段标注「随 BrickScene 退役」，弹层契约段保留并映射为 `overlay` 节点；新增声明式形态章节并回链本文 | Phase A | 小 |

## 6.2 BrickUIKit 复用边界

| 层 | 是否复用 | 说明 |
|---|---|---|
| Tokens（颜色 / 字号 / 间距 / 圆角 / 动效时长） | **完全复用** | 渲染器与 UI 文档的令牌名一一对应；UI 文档不接受自由样式值，保证与底座视觉零漂移 |
| Components（按钮 / 卡片 / 列表 / 表单控件） | **主体复用** | 渲染器为每个组件类型建立「节点 type → SwiftUI 组件」映射；缺失项按第二章清单补齐 |
| BrickOverlays（sheet / dialog / banner） | **复用** | 保留既有三契约的视觉与交互语义，映射为 `overlay` 节点的三个子类型 |
| BrickScene（窗口 / 生命周期 / 尺寸约束） | **退役** | 内嵌形态下窗口与尺寸约束由宿主外壳与主区域决定 |

**避免二次实现的规则**：渲染器**不得**新写一套样式常量；所有视觉值必须来自 Tokens。若某组件的既有实现与声明式语义冲突（如自由布局），以「调整既有组件」而非「在渲染器内另写一份」为准。

## 6.3 主区域宿主的演进

```
现 状：  mainArea ──> showWorkshop | activeNativeViewID(BrickViewRegistry) | 详情页
                      （产品积木不在此路径，走独立 .app 窗口）

目标态：  mainArea ──> showWorkshop | activeBrickSlot(BrickHostView → BrickRenderer) | 详情页
                      ├─ kind: builtin  → 既有注册表原生路径（不变）
                      └─ kind: product  → 渲染器 + 逻辑进程（新增）
```

| 演进项 | 现状 | 目标 | 兼容要求 |
|---|---|---|---|
| 槽位互斥 | 三态互斥已实现（`navigate(to:)` 强制清 `showWorkshop` / `activeNativeViewID`） | 增加 `activeBrickSlot` 为第三态成员 | 互斥语义不变，切换时对离开的积木发 `lifecycle/suspend` |
| 宽度适配 | 主区域实宽约 640~690pt（右栏 230~320pt） | 产品界面按 `ui/resize` 自适应（栅格列数随宽度变化） | 旧 760pt 最小宽假设**失效**，积木不得再假设窗口宽 |
| 单实例 | 依赖 `createsNewApplicationInstance`（曾为多实例根源） | 槽位唯一性天然单实例；重复入口只做激活置前 | 旧 `runningBricks` 多实例逻辑不再需要 |
| 关闭语义 | 积木自管窗口关闭（关窗即退） | 宿主外壳提供关闭/返回；离开槽位即 `suspend`，卸载才 `shutdown` | 用户不再能"关掉积木窗口"，只能切走或卸载 |

## 6.4 退役方案

### 退役对象与三条件

| 退役对象 | 前置条件（三条同时满足） |
|---|---|
| `BrickScene` + `BrickLifecycleView` + 独立窗口路径 | ①市场无 v1 积木在售；②无已装 v1 积木处于运行状态（含 vault / wechat-mp 已完成迁移）；③模板规格与市场文案已更新 |
| 桥 token 注入（`ENDPOINT` / `TOKEN` 环境变量） | 同上 |
| `createsNewApplicationInstance` 分支 | 同上 |

> **三条件达成记录（2026-10-09）**：① 市场无 v1 在售——`index.json` products 段全部为 v2（`wechat-mp` 1.2.1 / `vault` 1.2.2）；② 无 v1 在跑——两个产品均已完成 v2 迁移（Phase D / Phase E1），本机是否残留 v1 实例由 owner 真机核验；③ 模板规格与市场文案已更新——《积木规范化模板规格 v0.1》§1.3 标注退役并回链本节，市场与设置页无「旧形态」文案。

### 退役步骤

1. **标记期**（Phase D）：文档与市场标注「旧形态」；底座日志对 legacy 路径输出弃用警告；不再新增 v1 积木。
2. **拒绝新装期**（Phase E 初）：市场下架 v1 积木，本地安装器对 v1 新装弹出「该积木为旧形态，功能将逐步下线」提示（不强制拒绝，避免破坏用户既有资产）。
3. **代码删除期**（Phase E 末）：删除 `BrickScene.swift` / `BrickLifecycleView` / `openProductBrick` 的 legacy 分支 / 桥 token 注入。**已完成（2026-10-09）**：`BrickUIKit/BrickScene.swift`（含 `BrickLifecycleView`）物理删除；底座删除 `openProductBrick` / `issueBridgeToken` / `launchProductBrick` / `trackRunningBrick` 与 `runningBricks` / `bridgeTokenObservers` 状态、`productDescriptor` 双分支收敛、`openBrick` 的 `.product` 分支、`BrickWorkshopView` 的 `.product` 枚举项与 `TokenObserverBox`；`main.swift` 的 `createsNewApplicationInstance = true` 属自换装逻辑保留（见 §6.1）。
4. **文档回更**：模板规格窗口段标注「已退役（v0.2 起）」并回链本文；本文升版为 v1.0。**已完成（2026-10-09）**：本文升版 **v1.0**（文件更名 `Shadeling积木声明式UI架构设计与契约-v1.0.md`），模板 §1.3 已标注退役。

### 兼容期策略

| 项 | 约定 |
|---|---|
| 兼容期长度 | 上限 2 个小版本周期；到期即执行代码删除期 |
| 已装 v1 积木 | 兼容期内可正常运行；不自动卸载、不阻断 |
| 数据目录 | v1 → v2 迁移时私有数据目录沿用同一 `brick_id` 路径，向前兼容（只增字段不删） |
| 回滚 | 保留 feature flag `brick_declarative_channel`（Phase A 起灰度默认关）；出问题关闭即回到 legacy 路径 |

## 6.5 保持不变的红线与既有能力

- `BrickViewRegistry`「不做运行时动态加载」的编译期注册红线不变，第三方积木的"动态"仅体现为 UI 文档与逻辑进程，不进入视图注册表。
- 既有 brick-agent-bridge v0 的白名单工具、权限枚举命名空间（`agent.*`）、`429x` 配额口径、安装时高危标红机制全部保留。
- 主模型能力仅通过闸门提供（`agent.chat`），积木不获得直接模型调用通道。

## 6.6 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| E1 | 令牌与组件层完全复用，BrickScene 退役 | 视觉一致性的唯一可靠来源是令牌；窗口层在新形态下无对应物 |
| E2 | `NativeBrickHostView` 演进而非重写 | 三态互斥槽位与导航逻辑已验证，替换成本高于改造 |
| E3 | 注册表仅服务内置积木 | 保持编译期注册红线，避免第三方代码进入主进程视图层 |
| E4 | 退役以「市场无在售 + 无在跑」为前置条件 | 避免出现用户资产被强制中断 |
| E5 | 兼容期上限 2 个小版本 | 限制双形态并存的支持成本与测试矩阵膨胀 |
# 七、分阶段实施计划与验收

## 7.0 排期口径说明

本文以**相对周次**（W1 起算）表示阶段排期，绝对日历日期未提供，实施时由维护者按启动日折算。各阶段为串行推进，前置阶段验收未通过不得进入下一阶段。

## 7.1 阶段总览

| 阶段 | 目标 | 周次 | 出口门槛（一句话） |
|---|---|---|---|
| Phase A | 协议与渲染器骨架，打通最小闭环 | W1~W3 | 示例积木端到端跑通 + 崩溃可恢复 + v1 积木不回归 |
| Phase B | 组件扩充与更新策略 | W4~W6 | 10 类组件示例页全通过 + 增量更新达标 |
| Phase C | 隔离、权限与配额 | W7~W9 | 权限三重校验与配额降级全部可验证 |
| Phase D | vault 迁移 | W10~W12 | vault 功能对齐 + 数据不丢 + 不再依赖 BrickScene |
| Phase E | wechat-mp 迁移与老形态退役 | W13~W16 | 迁移范围对齐 + legacy 路径移除后全量回归通过 |

## 7.2 Phase A：协议与渲染器骨架（W1~W3）

| 任务 | 交付物 | 依赖 |
|---|---|---|
| A1 stdio 协议实现（底座侧 + 参考 SDK + 示例逻辑进程） | `BrickProtocol` 模块 + `bricks/demo-declarative`（含 `manifest.json` / `ui/main.json` / `logic/demo`） | 无 |
| A2 宿主外壳 `BrickHostView`（标题 / 返回 / 关闭 + 崩溃态容器） | 底座主区域新槽位 `activeBrickSlot` | 无 |
| A3 渲染器骨架：`container` / `text` / `button` / `progress` + 全量快照 + `tap` 事件 | `BrickRenderer` 模块（令牌取自 BrickUIKit） | A2 |
| A4 manifest v2 解析与安装分支（`kind: product` → 内嵌；`legacy-app` → 旧路径） | `InstalledBrickManifest` v2 支持 | 无 |
| A5 逻辑进程托管（spawn / 心跳 / 退出 / 重启 / 循环保护） | `BrickProcessSupervisor` | A1 |

**验收标准**

1. 示例积木在主区域完成渲染；点击按钮 → 事件回传 → 界面更新，端到端延迟 < 100ms（本地实测）。
2. 示例积木主动 `exit` → 槽位显示崩溃态（错误摘要 + 重启按钮）→ 点击重启后 3s 内恢复正常渲染。
3. 回归：v1 形态的 vault（独立 .app）在新底座上仍可正常打开与运行。
4. 推送非法 UI 文档（未知 type / 超深度）→ 保留上一有效帧 + 槽位内嵌错误提示，底座不崩溃。
5. 隔离验证：逻辑进程无窗口（进程无 WindowServer 连接）、无网络连接（`lsof -i` 无外连）。
6. 切换槽位（切工坊再切回）→ `suspend` / `resume` 生效，状态不丢。

## 7.3 Phase B：组件扩充与更新策略（W4~W6）

| 任务 | 交付物 | 依赖 |
|---|---|---|
| B1 补齐 `list` / `card` / `form` / `overlay` / `image` / `icon` | 渲染器组件映射 + BrickUIKit 组件补齐 | Phase A |
| B2 增量更新（路径 patch + state 局部更新） | `ui/update` 三模式 | Phase A |
| B3 主题切换与 `ui/resize` 自适应（栅格列数随宽度） | 主题令牌双套 + 自适应布局 | Phase A |
| B4 积木 SDK（Python / Node 最小库 + 示例） | `sdk/python`、`sdk/node` 最小实现 | A1 |

**验收标准**

1. 10 类组件示例页全部渲染通过，视觉与 BrickUIKit 现有页面一致（截图比对）。
2. 5000 行列表用 patch 追加 1 行，渲染耗时 < 50ms；全量快照模式下同一操作 < 200ms。
3. 主题切换（浅/深）与右栏展开/收起时无布局错乱，`ui/resize` 正确触发重排。
4. 节点数 / 深度 / 体积超限按 `4304` 整帧拒绝并给出违规节点路径。
5. 主区域最小实宽（约 640pt）下，示例积木界面无横向溢出。

## 7.4 Phase C：隔离、权限与配额（W7~W9）

| 任务 | 交付物 | 依赖 |
|---|---|---|
| C1 权限枚举扩展（UI 侧 7 项）+ 安装确认 UI（级别映射 + 高危二次确认）——**✅ 已落地（2026-10-03）· 真机验收通过（2026-10-07）** | `BrickPermission` 扩展 + 安装页 | Phase A |
| C2 运行时闸门（三重校验 + 违规计数 + 高危首调确认 + 审计日志）——**✅ 已落地（2026-10-04，底座侧 + 宿主侧）· 真机验收通过（2026-10-07）** | 闸门扩展 | C1 |
| C3 配额（事件频率 / 节点 / 内存 / 存储 / 重启保护）+ 超限降级提示——**✅ 已落地（2026-10-04）· 真机验收通过（2026-10-07）** | 配额模块 | C2 |
| C4 安装器 v2 校验 + `verify_products.py` 三项扩展——**✅ 已落地（2026-10-04）· 真机验收通过（2026-10-07）** | 安装器 + 发布闸门 | A4 |

> **C1 落地说明（2026-10-03，Shadeling 实现侧，工作树改动、未提交）**
> - 枚举：`BrickPermission` 拆为 `bridgeKnown`（桥 5 项，逐字未动）+ `uiSideKnown`（本契约 §5.2 的 UI 侧 7 项），`known` = 两者拼接；`uiSideHighRisk = []`（UI 侧无高危项显式落点）。
> - 级别映射：低 = `ui.sheet` / `ui.clipboard.write` / `notify`；中 = `ui.open_url` / `fs.pick` / `auth.biometric` / `ocr.recognize`；高 = `agent.browser` / `agent.local`；未知名按中危兜底（不静默提权）。未知值闸门按命名空间前缀（`agent.` / `ui.` / `fs.` / `auth.` / `ocr.`）判定。
> - `ui.sheet`：按 §5.2 / §5.6 的 2026-09-26 拍板实现为提示项（`hintOnly`；留在合法枚举内、按低危默认授权、确认页不渲染独立开关）。
> - 同步点：底座 `runtime/brick_bridge.py` 新增 `UI_PERMISSIONS`（7 项，与 `uiSideKnown` 逐项一致），`KNOWN_PERMISSIONS` = 桥 5 + UI 7；`PERMISSION_TOOLS` / `HIGH_RISK_PERMISSIONS` 未动。
> - 安装确认页：低危默认勾选、中危默认不勾、高危标红 + 二次确认弹窗；提示项灰标签仅列示。
> - 验证结果：`swift build` 零 warning（本轮改动文件）；`swift test` **255 tests / 0 failures**（含新增 `BrickPermissionPhaseCTests` 14 例）；`python3 -m unittest runtime.tests.test_brick_permission_ui_side` **12 tests OK**。（计数口径以 Shadeling `specs/state-2026-10-03.md` §11.4 为准。）
> - 尚未覆盖：安装确认页的真机目视验收（标红 / 提示项标签 / 二次确认弹窗）待开 flag 后走完整安装流程。

> **C2 落地说明（2026-10-04，Shadeling 实现侧，工作树改动、未提交）**
> - 底座侧：`runtime/brick_gate.py` 三重校验（「已声明 → 已授予 → 未超配额」）+ 违规累计 3 次置 `interrupt_session` + 首调确认与 `reentry` + 审计脱敏保留 30 天；`brick_bridge.py` / `ipc.py` 接 `declared_permissions` 与 `brick_capability_call`（只裁决、返回 `forward` 目标）；4309 / 4310 入 `error-codes.json`，IPC 方法数 105 → 106；测试 54 例（37 + 12 + 5）全绿。
> - 宿主侧四项（`app/Sources/ShadelingApp/BrickCapabilityHost.swift`，457 行）：① 能力转发——按回执 `forward` 转发到既有 handler（UI 侧 7 项），未注入能力面时保持一律回 4309 的旧行为；② 首调确认——`BrickCapabilityConfirmSheet`（允许本次 / 本会话允许 / 拒绝），允许后带 `confirm=true` 重入闸门、拒绝回 4309，经 `ContentView` 统一弹窗层上屏；③ 违规中断——`BrickProcessSupervisor.interruptSession(brickID:notice:)` 终止会话并落槽位提示（复用崩溃态容器族）；④ 市场质量统计——按本契约 §4.10 / §5.3.2 只定义聚合口径与展示方、**未定义宿主上报通道**，本轮不做投递，以 `BrickQualityNotes` 显式登记该结论，底座登记侧不变。
> - 验证：`swift test` **313 tests / 0 failures**（新增 `BrickCapabilityHostTests` 17 例）。
> - 待 owner 定：市场质量统计的宿主上报通道（端点 / 鉴权 / 批量口径）。待真机验收：确认弹窗三态与 `confirm=true` 重入、违规 3 次中断的槽位提示。

> **C3 落地说明（2026-10-04，Shadeling 实现侧，工作树改动、未提交）**
> - 底座：`runtime/brick_quota.py`（1172 行）——事件频率默认 30/s（manifest 可收紧 1~120，超频丢弃并按 4306 降级）、单帧节点数 2000 / 嵌套深度 16 / JSON 体积 512 KB（超限按 4304 拒帧）、内存软上限 512 MB 警告 + 1 GB 强制重启 4308、私有存储默认 128 MB 超限拒写 4310、重启保护 60s 内 3 次；**manifest 只能收紧不能放宽全局上限**；只做裁决与登记、不产生副作用。
> - 接线：`ipc.py` 新增五个宿主面方法 `brick_quota_ui_event` / `brick_quota_ui_frame` / `brick_quota_memory` / `brick_quota_storage` / `brick_quota_restart`（收参数、回判据；杀进程 / 拒写盘 / 出横幅由宿主按回执执行），`RuntimeQuotaGuard` 实例化于 `ipc.py`。
> - 宿主：`BrickQuotaHost.swift`（227 行）回执 → 呈现映射（4308 复用崩溃态容器并标注「已自动重启」；4310 复用槽位 banner），`BrickProcessSupervisor.noteQuotaDecision` / `quotaNotice` / `clearQuotaNotice` 落句柄。
> - 验证：`test_brick_quota` 32 + `test_brick_quota_ipc` 25 + `test_brick_quota_runtime` 31 = 88 例 OK；`swift test` **313 tests / 0 failures**（新增 `BrickQuotaHostTests` 10 例）。待真机验收：内存强杀、存储拒写、重启保护、超频降级横幅。

> **C4 落地说明（2026-10-04，Shadeling 实现侧 + 本仓发布侧，工作树改动、未提交）**
> - 宿主安装器：`app/Sources/ShadelingApp/BrickInstallGate.swift`（404 行）——§3.6-1 字段级规则（元数据 / nav / ui.theme / logic.args / logic.env / legacy 误用，含凭据样式串识别）、§3.6-2 跨包语义（`brick_id` 唯一性 + 同 id 版本单调递增）、§3.6-5 quota 钳制警告记录、§3.6-6 UI 文档离线预校验（含图片引用必须落在包内）；`AppModel` 安装流程接入（`validate` / `installedManifests` / `quotaWarnings`，警告写入快照 `quota_warnings`）。
> - 发布闸门（本仓 `scripts/verify_products.py`，+179 行）：声明式（`brick-app/v2`）三项扩展 —— ① `ui.entry` 存在且在包内可解析（§2.2 / §2.3 / §2.7：schema、节点类型白名单、节点 id 文法、节点数 2000 / 深度 16）；② 无裸弹层调用（弹层必须写成 `overlay` 节点 + 子类型，含系统弹层别名拦截）；③ `logic.entry` 已登记哈希或签名（`manifest.logic.sha256` 64 位十六进制，或 `manifest.logic.signature` 前缀 `shadeling-sig/v1:`，仅格式与一致性校验）。`ZIP_MANIFEST_FIELDS` 增补 `nav` / `ui` / `logic`；v1（bundle 形态）在兼容期不适用本组检查。
> - 验证：`python3 -m unittest discover -s tests` **51 tests OK**（`test_verify_products` 31 + `test_verify` 12 + `test_pack_product` 8）；宿主 `BrickInstallGateTests` 29 例全绿。
> - 待 owner 定：`logic.entry` 真实验签、`logic.env` 键白名单、`ZIP_MANIFEST_FIELDS` 增补口径与 v2 是否强制 `bundle` / `permissions` 硬卡点。待真机：装包负例验收。

> **契约同步说明（2026-10-06，本仓，随本仓 commit 提交）** —— 承接 Shadeling `specs/state-2026-10-03.md` §16：owner 于 2026-10-06 按建议拍板 **C / A / B / B**（`logic.entry` 取 C、v2 强制段取 A、`logic.env` 取 B、quota 警告 UI 可见取 B），宿主侧代码与单测已落地，本仓按同源判据同步：
> - §3.3：`logic.env` 由「黑名单描述」改为**显式正列举白名单**（首批为空集 = `logic.env` 必须为空对象；放行具体键须先做「底座 ↔ 契约」同步登记，禁止前缀 / 通配放行）；新增 `logic.sha256` / `logic.signature` 登记字段（二者至少其一，判据 C），原「2026-10-04 补充判定」转正并在 §3.6 校验清单中列为独立注记。
> - §3.5：兼容矩阵新增「v2 缺 `nav` / `ui` / `logic` 任一 → 拒装」硬卡点行（拍板 A），并补「v1 不强制三段」行。
> - §3.6：新增第 1 项**三段早检硬卡点**（含文案，且早检先于字段级文案报出）与第 5 项 `logic.env` 白名单；原发布闸门项（四项同源）扩为四项检查说明。
> - `scripts/verify_products.py`：新增常量 `REQUIRED_SECTIONS` / `ALLOWED_LOGIC_ENV_KEYS` 与 `verify_required_sections` / `verify_logic_env`，并接入 `verify_v2_declarative_gates`（顺序：三段早检 → `logic.env` 白名单 → 包内 `ui.entry` / `logic.entry`）；`ZIP_MANIFEST_FIELDS`（含 `nav` / `ui` / `logic`）与 `SHA256_RE` / `SIGNATURE_PREFIX` 复核确认与宿主判据同源，未变动。
> - 验证：`python3 -m unittest discover -s tests` **60 tests OK**（原 51 例 + 本次新增 9 例：三段硬卡点 4 / `logic.env` 白名单 5）。
> - 勾销：§7.4 C4「四项待 owner 定」按 2026-10-06 拍板结论勾销（见下）。

> **§7.4 C4 待定项勾销（2026-10-06 owner 按建议拍板 C / A / B / B）**
> - ~~`logic.entry` 真实验签~~ → 取 **C：本轮不做**真实验签，仅做登记 + 格式 / 一致性校验；真实验签留到对外分发（随付费开发者账号 + 公证一并做）。
> - ~~`logic.env` 键白名单~~ → 取 **B：显式正列举**，首批为空集（§3.3 / §3.6-5）。
> - ~~`ZIP_MANIFEST_FIELDS` 增补口径~~ → 已含 `nav` / `ui` / `logic`，与宿主同源（§3.6-9）。
> - ~~v2 是否强制 `bundle` / `permissions` 硬卡点~~ → 取 **A：强制 `nav` / `ui` / `logic` 三段**（§3.5 / §3.6-1）；`bundle` 对 v2 不适用，`permissions` 仍按 §5 枚举校验（不做「必须非空」硬卡点）。
> - 仍待 owner 定（不在本次拍板范围）：市场质量统计通道（§4.10 / §5.3.2 的宿主上报端点 / 鉴权 / 批量口径，见 C2 落地说明）。
> - 待真机：装包负例验收（C4 五类负例，宿主侧离线预验已在 Shadeling 侧完成）。

> **Phase C 真机验收记录（2026-10-07，owner 真机操作 / Marvis 记录）** —— 来源 Shadeling 仓 `specs/phase-c-acceptance-2026-10-07.md`（含操作序列 / 审计日志 / 截图清单 / 验收红线）：
> - 被测：`Shadeling-0.5.8.app`（实例 PID 80822），夹具源 `vault-0.5.8/`（env `SHADELING_BRICK_VAULT` 指向，9 条 acct-* 夹具）。
> - **C1**：5 条非法负例（acct-c1-*）安装期全部拒装，页面红字与 os_log 一致、`Bricks/` 零残留；安装确认页目视通过（含 quota 钳制警告区块）。
> - **C2**：首调确认卡三态（允许本次 / 本会话允许 / 拒绝）、`confirm=true` 重入、未声明能力 `4309`、违规×3 中断槽位提示全部符合契约；「本会话允许」会话级免重弹（同会话第三次调用直接放行）与「拒绝」按未授权路径结案（不产生会话记忆、`violations` 保持 0）已补测取证。
> - **C3**：`acct-quota-clamp` 配额钳制确认页如实列出四键收紧项（500→120 / 99999→5000 / 4096→2048 / 8192→2048），确认后落盘；内存强杀 / 存储拒写 / 重启保护 / 超频降级的底座裁决面 2026-10-05 离线全量通过（20/20），真机 `4306` 超频降级与 `4308` 内存强杀提示复验通过。
> - **C4**：3 条 UI 文档非法样例（未知组件 / `kind` 非法 / 未知组件 `sheet`）按 `4303` 拒装，违规节点路径与 os_log 一致。
> - 同日收尾修复：越权中断角标改「已中断」（`BrickCrashPresentation` 三态）、工坊「重新加载清单」回本地源（原直连 GitHub raw 会覆盖自建源清单）、卸载 tooltip 校正；Shadeling 侧提交 `bc71a53`、`6bc6e0b`，回归 `swift test` 345 例 0 失败。
> - 仍待验证（不在本次范围）：v2 缺 `nav` / `ui` / `logic` 任一段拒装、`logic` 段无 `sha256` / `signature` 拒装、`logic.env` 含未列举键拒装三条负例（待 0.5.9 出包后复验）。
> - 遗留观察：拦截文案未带契约条款号（可选收敛）；`interrupted` 事件疑似双写（seq7 / seq8 时间戳相同）；审计中「拒绝」与「取消」不可区分、无 `denied` 回执（若契约要求拒绝路径可审计，需单独补留痕）。

**验收标准**

1. 未在 manifest 声明的能力调用被拒（`4309`）并计违规；累计 3 次后槽位提示并中断会话。
2. 高危权限在安装页标红 + 默认不勾选；勾选后弹二次确认；首次实际调用仍弹一次性确认。
3. 逻辑进程内存达 1 GB 被强制重启（`4308`）；60s 内重启 3 次后停止自动重启并提示。
4. 事件超频（> 30/s）被丢弃并显示降级横幅（`4306`）。
5. 离线预校验可拦截含未知节点类型、路径逃逸、远程图片引用的样例积木，并输出违规节点路径。
6. `verify_products.py` 三项新检查对样例负例全部拦截（可复现）。
7. 设置页可查看并撤销任一积木的权限与配额使用。

## 7.5 Phase D：vault 迁移（W10~W12）

| 任务 | 交付物 | 依赖 |
|---|---|---|
| D1 vault 业务状态机从 SwiftUI 抽离为逻辑进程 | `logic/vault` | Phase B、C |
| D2 UI 文档编写（命令栏 / 筛选栏 / 卡片墙 / DetailSheet / ManualAddSheet） | `ui/*.json` | D1 |
| D3 能力代理：`auth.biometric`（Touch ID）、`ocr.recognize`（OCR） | 底座能力 + 权限项 | Phase C |
| D4 数据迁移（私有目录、加密库位置、`brick_id` 不变） | 迁移脚本 + 校验 | D1 |

**验收标准**

1. 功能对齐清单逐项通过：检索、筛选、卡片墙、详情、手动新增、OCR 录入。
2. 生物识别解锁与 OCR 录入可用，且权限未授予时给出明确提示而非静默失败。
3. 卸载重装后私有数据不丢；v1 → v2 迁移前后数据条目数与校验和一致。
4. vault 不再依赖 BrickScene / 独立窗口（依赖检查：产物中无窗口相关符号）。
5. 主区域 640pt 最小宽度下可用；栅格列数随宽度自适应。

## 7.6 Phase E：wechat-mp 迁移与老形态退役（W13~W16）

| 任务 | 交付物 | 依赖 |
|---|---|---|
| E1 wechat-mp 可表达部分迁移（草稿列表 / 发布表单 / 媒体管理 / 账户） | `ui/*.json` + `logic/wechat-mp` | Phase D |
| E2 硬瓶颈替代方案落地（Markdown 编辑 / HTML 预览） | 决策结论 + 实现或延后说明 | E1 |
| E3 legacy 路径退役（移除 `NSWorkspace` 打开 .app、桥 token 注入、`createsNewApplicationInstance`） | 代码删除 + 文档回更（**2026-10-09 完成**，见 §6.4） | E1、E2 |
| E4 本文升版 v1.0；模板规格窗口段标注退役 | 文档（**2026-10-09 完成**：本文升版 v1.0 + 模板 §1.3 标注退役） | E3 |

**验收标准**

1. wechat-mp 迁移范围内功能对齐（列表 / 发布 / 媒体 / 账户四块）；未迁移界面有明确说明与入口提示。
2. E2 决策结论落地：若采用混合模式，需给出可复现的操作路径与用户提示文案。
3. 删除 legacy 路径后全量回归通过（含 v2 积木与内置积木）。
4. 市场与设置页无「旧形态」残留文案；`verify_products.py` 无 legacy 兼容分支。
5. 无 v1 积木在售、无 v1 积木在跑（可由市场与本地登记表核验）。

> **验收状态（2026-10-09，Phase E 收口）**：①/② wechat-mp 迁移范围（草稿列表 / 发布表单 / 媒体管理 / 账户）由 `releases/1.2.1` 包 + `ui/main.json` + `logic/wechat_mp` 承载，真机目视待 owner；③ 删除 legacy 路径后全量回归通过（`swift build` / `swift test` / `verify_products.py` / `verify_ui_doc.py` 全绿，内置积木与 v2 积木路径未受影响）；④ 市场与设置页无「旧形态」文案，`verify_products.py` 无针对 legacy .app 形态的专用检查（§3.5 兼容期对 v1 包的放行由兼容期矩阵定义，非 legacy 专用分支）；⑤ `index.json` 在售清单已无 v1，本机无 v1 在跑由 owner 真机核验。

## 7.7 里程碑与量化指标

| 里程碑 | 指标 |
|---|---|
| M1（Phase A 出口） | 端到端事件延迟 < 100ms；崩溃恢复 < 3s；v1 回归 100% 通过 |
| M2（Phase B 出口） | 10 类组件覆盖；patch 更新 < 50ms（5000 行列表） |
| M3（Phase C 出口） | 权限/配额负例拦截率 100%（样例集） |
| M4（Phase D 出口） | vault 功能对齐 100%；数据迁移校验和一致 |
| M5（Phase E 出口） | legacy 代码零残留；全量回归 100% 通过 |

## 7.8 风险与预案

| 风险 | 触发条件 | 影响 | 预案 | 止损阈值 |
|---|---|---|---|---|
| 协议返工 | Phase A 出口前发现帧格式 / 握手 / 生命周期设计无法覆盖真实场景 | 全部积木与 SDK 返工 | Phase A 内冻结协议，后续只增方法不改旧语义；破坏性变更需新协议版本号 | Phase B 起破坏性变更次数 = 0 |
| 组件表达力不足 | 迁移中界面无法表达且无替代路径 | 迁移受阻、体验降级 | 走底座能力代理（新增受控能力）或降级表达；**不开放自定义绘制** | 单积木不可表达界面占比 > 20% → 暂停迁移并重评组件集 |
| 迁移超期 | Phase D 超过 3 周预算 | 拖累 Phase E | 缩减范围（先迁核心 3 界面），生物识别 / OCR 延后 | 超期 1 周即启动范围裁剪 |
| 兼容期混乱 | 用户同时遇到 v1 与 v2 两种形态，支持与测试成本上升 | 体验不一致、问题定位困难 | 市场与设置页显式标注形态；固定兼容期上限 2 个小版本 | 兼容期超过 2 个小版本即强制进入删除期 |

## 7.9 回滚方案

| 层级 | 回滚手段 |
|---|---|
| 通道级 | feature flag `brick_declarative_channel`（Phase A 起默认关、灰度开）；关闭即回 legacy 路径 |
| 阶段级 | 每阶段结束打 git tag（`brick-v2-phaseA` … `phaseE`），可整体回退 |
| 积木级 | Phase D 迁移期双跑：旧 vault `.app` 保留在本地私有目录可回退；数据目录向前兼容（只增字段不删） |
| 发布级 | `verify_products.py` 作为发布闸门，未通过不得上架 |

## 7.10 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| F1 | Phase A 设硬门槛（端到端 + 崩溃恢复 + 回归） | 协议是全部后续工作的地基，早期返工代价最高 |
| F2 | 组件集在 Phase B 定稿，之后只增不改语义 | 避免迁移期间组件契约漂移 |
| F3 | 迁移顺序 vault → wechat-mp | vault 可行性更高，先验证通路再挑战硬瓶颈 |
| F4 | legacy 退役以代码删除为完成标志（非文档声明） | 避免出现"文档说退役、代码仍可达"的滞后 |
| F5 | 全程 feature flag + 阶段 tag | 保证任一阶段可回滚，控制内嵌形态切换风险 |
# 八、vault 与 wechat-mp 迁移可行性评估

## 8.1 评估方法

以第二章「首批组件清单 + 不支持场景清单」为判据，对两仓每个界面逐项判定，分三档：

| 档位 | 判据 |
|---|---|
| **可** | 界面所有元素均能用首批组件表达，且无需新增底座能力（或仅需低危权限） |
| **部分可** | 主体可表达，但存在 1~2 处需新增底座能力代理或需降级表达的元素 |
| **不可** | 存在无替代路径的元素（如富文本渲染、WebView），迁移后功能将缺失 |

判定依据来自本仓与两积木仓的实际界面结构（`ContentView` / `ManualAddSheet` / `DetailSheet` / OCR 相关视图；草稿列表、编辑、发布、媒体、账户、HTML 预览等视图），不凭界面名称推断。

## 8.2 vault 逐界面评估

| # | 界面 | 主要元素 | 档位 | 组件映射 | 瓶颈 / 缺口 |
|---|---|---|---|---|---|
| 1 | 命令栏 | 搜索输入、新增按钮、批量操作按钮 | **可** | `container`(horizontal) + `form.field` + `button` | 无（搜索防抖需逻辑进程侧处理） |
| 2 | 筛选栏 | 分类分段选择、排序下拉、标签筛选 | **可** | `picker(mode=segment)` / `picker(mode=menu)` | 无 |
| 3 | 卡片墙 | 网格卡片、标题、摘要、标签、相对时间、徽标、缩略图 | **可** | `grid` + `card` + `text` + `icon` + `image` | 列数需随主区域宽度自适应（`ui/resize`）；卡片悬停/选中样式由渲染器统一提供 |
| 4 | DetailSheet（详情） | 字段列表、复制字段值、编辑/删除操作 | **可** | `sheet` + `container` + `text`(mono) + `button` | 复制需 `ui.clipboard.write`（低危）；删除需 `dialog` 危险确认 |
| 5 | ManualAddSheet（手动新增） | 多字段表单、必填校验、字段级错误、提交 | **可** | `sheet` + `form`(field/textarea/picker/toggle) + `submit` | 校验逻辑与错误文案由逻辑进程返回；字段联动需一次往返 |
| 6 | OCR 录入 | 选图、识别进度、识别结果回填表单 | **部分可** | `image` + `progress`(indeterminate) + `form` | 需新增 `fs.pick`（选图）与 `ocr.recognize`（本地识别）；识别无实时进度回调，只能不确定态展示 |
| 7 | 生物识别解锁 | Touch ID 验证、失败重试提示 | **部分可** | `dialog` + `banner` 提示 | 需新增 `auth.biometric` 能力代理；无声明式原生替代 |

**vault 结论**：**可行性高**。7 个界面中 5 个完全可表达，2 个（OCR 录入、生物识别解锁）通过新增两项底座能力代理（`ocr.recognize` / `auth.biometric`）即可闭环，**无硬瓶颈**。需新增权限：`fs.pick`、`ocr.recognize`、`auth.biometric`、`ui.clipboard.write`（均属中/低危，无需高危标红）。

**迁移注意点**

1. 卡片墙列数不得写死，必须随主区域宽度（约 640~690pt 实宽）自适应；旧 760pt 最小宽假设作废。
2. 加密数据的读写全部在逻辑进程内完成，底座不接触密钥材料；私有目录路径由 `initialize` 下发（同一 `brick_id` 保证迁移后路径不变）。
3. OCR 识别耗时较长（图片较大时），需以 `progress` 不确定态 + `banner` 提示承载，避免界面假死。

## 8.3 wechat-mp 逐界面评估

| # | 界面 | 主要元素 | 档位 | 组件映射 | 瓶颈 / 缺口 |
|---|---|---|---|---|---|
| 1 | 根导航 | 分段导航、页面切换 | **可** | `container` + `picker(mode=segment)` | 多视图切换由积木内部状态驱动（v2 无 `views[]`） |
| 2 | 草稿列表 | 列表项、标题、摘要、时间、状态徽标、操作按钮 | **可** | `list` + `card` + `text` + `badge` | 无（草稿量级远低于 5000 行上限） |
| 3 | 编辑器（Composer） | 标题输入、正文 Markdown 编辑、工具栏（插入格式）、字数统计、**实时预览** | **部分可 / 局部不可** | `form.field` + `form.textarea`(mono) + `button` + `text` | **硬瓶颈：Markdown 实时渲染无组件可表达**；工具栏插入语法可由按钮实现，字数统计可由 `text` 表达 |
| 4 | 发布设置 | 分组选择、定时开关、时间选择、可见范围 | **部分可** | `form.picker(menu/toggle/date)` | 时间选择仅有 `picker(mode=date)`（日期粒度），**无时间（时分）选择器**；需降级为「日期 + 手动输入时间」两字段 |
| 5 | 媒体管理 | 图片网格、缩略图、上传、删除、大图预览 | **部分可** | `grid` + `image` + `button` + `sheet` | 本地选图需 `fs.pick`；**上传属网络写操作，现有 `agent.web` 仅只读抓取，须走受控网络写 `agent.web.write`（§5.3.8，2026-10-09 立项）**；大图仅可展示，不可裁剪/编辑 |
| 6 | 账户信息 | 账户资料、配置项、开关 | **可** | `text` + `form` + `toggle` + `button` | 无 |
| 7 | HTML 预览 | 渲染 HTML 内容（WebView 预览） | **不可** | — | **硬瓶颈：v1 组件集无 WebView / HTML 渲染节点**，且远程内容加载与脚本执行与隔离红线冲突 |

**wechat-mp 结论**：**可行性中等，建议延后**。7 个界面中 4 个可表达、2 个部分可、1 个不可；硬瓶颈集中在三处：①Markdown 渲染；②HTML 预览；③媒体上传（网络写）。

## 8.4 硬瓶颈清单与建议

| 瓶颈 | 涉及界面 | 能力缺口 | 短期替代 | 中期建议 |
|---|---|---|---|---|
| Markdown 渲染 | 编辑器实时预览 | 无 Markdown / 富文本组件（`text` 明确不支持） | 编辑区用 `textarea`(mono) 承载源码，预览降级为「导出为本地文件 + 系统打开」 | 评估新增受限 `markdown` 节点：白名单语法子集 + 令牌样式 + 禁止内联 HTML / 脚本 / 远程图片 |
| HTML 预览 | HTML 预览 | 无 WebView 节点 | 不可替代（可降级为源码文本展示） | 评估受限 `webview` 节点：禁脚本、禁远程加载、仅允许包内或底座代理的本地 HTML，并单列高危权限 |
| 网络写（上传 / 草稿增删 / 发布提交） | 媒体管理、编辑页、草稿页、发布页 | `agent.web` 仅只读抓取 | 宿主 handler 未就绪前，引导用户手动保存到指定目录 | **已立项（2026-10-09）**：新增受控网络写 `agent.web.write`——host 白名单仅 `api.weixin.qq.com`、显式 method/body、multipart 受控、凭据仅留逻辑进程私有目录且不入日志不入桥、高危标红 + 首调二次确认 + 审计留痕（§5.3.8 / 评审记录） |
| 时间（时分）选择 | 发布设置 | 表单仅有日期粒度选择器 | 拆为「日期选择 + 时间文本输入」两字段 | 为 `picker` 增加 `mode=time` |
| 大图预览与编辑 | 媒体管理 | `image` 不支持滤镜/裁剪 | 仅展示 | 不做（编辑类能力超出声明式边界） |
| 生物识别 / OCR | vault 解锁与录入 | 无对应能力 | 不可替代 | 新增 `auth.biometric` / `ocr.recognize` 能力代理（本文已纳入 Phase D） |

## 8.5 迁移策略建议

| 积木 | 建议档位 | 时机 | 理由 |
|---|---|---|---|
| vault | **全量迁移** | Phase D（W10~W12） | 无硬瓶颈，仅需两项能力代理与四项中低危权限；可完整验证声明式通路 |
| wechat-mp | **部分迁移 + 瓶颈延后** | Phase E（W13~W16） | 列表 / 发布 / 账户 / 媒体（除上传）可先迁；编辑器与 HTML 预览待组件集评估结论 |

**wechat-mp 两阶段建议**

1. **第一阶段（Phase E）**：迁移根导航、草稿列表、发布设置（降级时间选择）、账户信息；媒体管理做展示、复制、删除与**上传**（上传依赖受控网络写 `agent.web.write`，已立项；宿主 handler 未就绪前按 `upload_blocked` 横幅降级告知）；编辑器降级为纯文本编辑 + 源码预览。
2. **第二阶段（v1.1 组件集评估后）**：若受限 `markdown` / `webview` 节点通过安全评审，则补齐编辑器预览与 HTML 预览；若未通过，则维持「导出 + 系统打开」的替代路径，并在市场页明确标注能力差异。

**混合模式的边界**：不建议长期保留「wechat-mp 独立 .app + 其余积木内嵌」的双形态，因兼容期上限为 2 个小版本（见第六章）；混合仅作为第一阶段过渡，需在第二阶段给出终态结论。

## 8.6 可行性汇总

| 积木 | 界面总数 | 可 | 部分可 | 不可 | 需新增权限 | 需新增能力 | 结论 |
|---|---|---|---|---|---|---|---|
| vault | 7 | 5 | 2 | 0 | `fs.pick`、`ui.clipboard.write`、`ocr.recognize`、`auth.biometric` | OCR、生物识别 | 可全量迁移 |
| wechat-mp | 7 | 4 | 2 | 1 | `fs.pick`、`ui.clipboard.write`、`agent.web.write`（高危，2026-10-09 立项） | 受限 `markdown` / `webview`（待评估）；受控网络写已立项 | 部分迁移：除 HTML 预览按 B1 降级外均可迁 |

## 8.7 决策基线

| 编号 | 决策 | 理由 |
|---|---|---|
| G1 | vault 作为首个全量迁移试点 | 无硬瓶颈，可完整验证协议、渲染器、权限与配额全链路 |
| G2 | wechat-mp 不阻塞 Phase D，按「部分迁移 + 瓶颈延后」处理 | 避免单只积木的组件缺口拖慢整体演进 |
| G3 | 不为迁移而放宽隔离红线（不放行任意脚本 / 远程加载） | 受限节点须单独安全评审，不得以"迁移便利"为由降低标准 |
| G4 | 上传类写能力按高危处理 | 写操作影响面大于只读抓取，须标红并二次确认（2026-10-09 评审后以受控网络写 `agent.web.write` 落地，见 §5.3.8） |
| G6 | 受控网络写按最小授权面落地：host 白名单 + 显式 method/body + 凭据仅留逻辑进程私有目录且不入日志不入桥 | 写操作不可逆且底座不得托管用户凭据；白名单扩展须走契约修订，不许 manifest 自定义 host |
| G5 | 混合形态仅作过渡，设明确终态期限 | 与第六章兼容期上限 2 个小版本一致 |
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
