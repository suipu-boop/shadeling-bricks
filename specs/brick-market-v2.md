---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_f5487cc6a93311f1aed8525400dcc5b3
    ReservedCode1: kHbkzS3Dk/LfVSdqWNjw0yiYLXHX8j2D9hBi/KEZSUbLg96JF7yjeRsIzRh1vim11fEQJTlzhxoJNLCFSt2lMHHvYDBDweubH4wMCRvGjKUsCS7pXHCwQS6VbHhObxL/StHQxBH2wgtATHGNQ0ce8c3wljAZCjLV2i58Dl/Bd1cWiBygmYzjwBD3Djo=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_f5487cc6a93311f1aed8525400dcc5b3
    ReservedCode2: kHbkzS3Dk/LfVSdqWNjw0yiYLXHX8j2D9hBi/KEZSUbLg96JF7yjeRsIzRh1vim11fEQJTlzhxoJNLCFSt2lMHHvYDBDweubH4wMCRvGjKUsCS7pXHCwQS6VbHhObxL/StHQxBH2wgtATHGNQ0ce8c3wljAZCjLV2i58Dl/Bd1cWiBygmYzjwBD3Djo=
---

# Shadeling 积木市场 V2：独立积木包 + 真实下载安装

> 状态：**已拍板，实施中**（2026-09-05）
> 权威实现：Shadeling app（安装器 / 工坊 UI）+ 本仓库（brick-vault / shadeling-bricks，积木包发布区）
> 本文是市场与库改造的契约文档；实现变更须同步本文。

## 一、决策记录（用户拍板）

1. **不要预置、不要假下载**：下载了就是真装进去，不下载就是干干净净一个 app。
2. **放弃图纸/解释引擎路线**：运行时解释执行效果不稳定、体验降级，不做。
3. **积木 = 独立编译的小程序包（bundle）**：稳定、界面自由度完全，从 GitHub 库真实下载安装。
4. **底座系统工具与市场彻底分离**：对话工具、诊断、任务、技能、MCP/规则/备份/引擎等系统能力直接绑定底座，是 app 不可分割的一部分；**不出现在积木市场、不给安装/卸载入口、不写"已安装/内置"标签**。
5. 唯一代价确认：积木以独立程序形态运行（独立窗口），由 Shadeling 作为聚合底座管理启动/卸载；窗口风格统一靠玻璃风设计规范 + 共享资源包维持。

## 二、生态边界（最终形态）

| 层 | 内容 | 分发 | 安装/卸载 |
|---|---|---|---|
| 底座（Shadeling） | 聊天核心、对话工具、诊断/任务/技能/设置等系统页、内核与 IPC 能力 | 随 app | 无（不可安装卸载） |
| 产品积木 | 独立小程序包，自带完整原生界面 | GitHub 库真实下载 | 有（安装/卸载/更新） |

现有声明式"积木"（brickery-runtime 时代 24 条）全部是底座能力的前身，按归属收编进底座或退役，**不再作为可安装积木**。

## 三、积木包规范（独立小程序包）

### 3.1 包形态

市场下载的最小单元是 **zip**，解压后为一个自包含 bundle，两种允许形态：

- **独立 app bundle（推荐）**：`<id>.app/`，任意复杂度的 SwiftUI/AppKit 界面，自行开窗口。
- **CLI/服务包（暂缓，仅预留）**：可执行文件 + 协议，宿主进程驱动。

发布物在仓库内以**源码 + 构建产物**两种形态管理（见第四章），市场安装的是构建产物 zip。

### 3.2 manifest（BrickManifest.json，草案）

```
{
  "schema": "brick-app/v1",
  "id": "com.shadeling.brick.<id>",      // 全局唯一
  "name": "<id>",                          // 短名，与目录一致
  "title": "显示名",
  "version": "1.0.0",
  "author": "Shadeling",
  "summary": "一句话简介",
  "kind": "product",                       // 固定 product：可下载安装的产品积木
  "bundle": "Shadeling<Id>.app",           // 解压后入口 bundle 名
  "icon": "icon.png",
  "min_os": "15.0",
  "permissions": [],                       // 预留：麦克风/摄像头/网络等用途声明
  "download_url": ".../<id>/<version>/<id>-<version>.zip",
  "sha256": "...",                         // 安装校验
  "release_notes": "…"
}
```

### 3.3 安装与数据目录

- 安装：下载 zip → 校验 sha256 → 解压到 `~/Library/Application Support/com.shadeling.app/Bricks/<id>/<version>/` → 登记版本 → 出现在积木列表。
- 打开：`NSWorkspace.open` 启动独立程序（未来可升级为受控 XPC 拉起）。
- 卸载：删除包目录 + 移除登记 + 可选清理积木私有数据目录。
- 更新：按清单比对版本，下载新版本替换并保留旧版回滚位。
- 安全：仅接受官方 GitHub 源与签名/哈希校验；manifest 字段白名单解析。

## 四、GitHub 库（brick-vault / shadeling-bricks）目录改造

```
brick-vault/
├── index.json               # V2：仅列 kind=product 可安装积木（schema: brick-registry/v2）
├── products/                # 【新】产品积木发布区
│   └── <id>/
│       ├── manifest.json    # = BrickManifest.json（3.2）
│       ├── source/          # 积木源码（可选：方便审阅/本地构建）
│       └── releases/
│           └── <version>/<id>-<version>.zip + .sha256
├── archive/                 # 【新】老声明式积木退役区（不入市场，仅留档）
│   └── bricks/…             # 原 bricks/ 下 24 条迁移至此
├── skills/                  # 保留：技能库（走技能页，不与积木市场混淆）
├── scripts/                 # verify 更新为 V2（manifest 校验 + zip 哈希 + 唯一性）
└── specs/                   # 契约文档（本文件等）
```

V2 index.json：

```
{ "schema": "brick-registry/v2",
  "bricks": [ { "name": "<id>", "kind": "product", "version": "1.0.0",
                "title": "…", "summary": "…",
                "download_url": "…", "sha256": "…" } ] }
```

### 迁移动作（本地实施顺序）

1. index.json 改 V2 schema，初始为空 `bricks: []`（app 侧已兼容空目录=空态）；
2. `bricks/` 下老声明式积木 → `archive/bricks/`（代码留档不删）；
3. 需要保留为底座的能力在 Shadeling app 内已有对应页面/配置（诊断/任务/技能/MCP/规则/备份/引擎/对话工具），无页面残留的老 IPC 条目随底座代码收编或退役；
4. 后续每上架一个产品积木：products/<id>/ 建目录、过 scripts/verify V2 闸门、push。

## 五、Shadeling 安装器（app 端实施记录）

### 5.1 已完成（2026-09-05）

- `MarketBrickItem` 增加 `kind` 字段；`isMarketEligible` 仅 `kind == "product"` 才进市场；
- `AppModel.loadMarketBricks / loadMarketBricksFromRemote` 统一过滤 product；空目录是合法空态，不再误报错误；本地旧 V1 清单解析为空时自动回退拉 GitHub；
- 市场页副标题改为「从 GitHub 积木库下载安装独立积木包」；
- 市场空态文案明确：系统能力已随底座内置，无需也不可在此安装。

效果：底座系统工具（含老 24 条声明式条目）**不再出现在市场**，不再有任何"已安装/内置"标签；当前市场为空（V2 目录未上架任何产品积木）。

### 5.2 待实施（V2 安装器）

- `BrickPaths`：新增安装根目录 `Bricks/<id>/<version>/`、manifest 读取、sha256 校验；
- `installBrick` 重写：product zip 下载 → 校验 → 解压 → 登记 → 打开（替代现行"下载 brick.json 到本地 brick-vault"逻辑）；
- `uninstallBrick`：删除包与登记（现行仅移除登记）；
- 已装卡片墙：过渡期保留 vault / ppt-studio / cabinet 内置墙；待现有四只产品化决策后按 §7 迁移。

## 六、底座系统工具绑定清单（不进市场）

以下能力随 Shadeling app 提供，市场不出现：

- 对话工具（快捷条开关）：ax、browser、code-quality-chain、hello-marvis、meeting-minutes、visualize
- 系统页/子系统：doctor（诊断）、scheduler/multi-agent（任务）、skill-library（技能）、mcp、rules、backup-restore、engine-local/engine-api（设置）
- 文档生成 docwrite / high-config-doc：并入技能体系（SkillsView）
- 连接器 feishu / telegram / agent-mail 老声明式形态：不再作为可安装积木；agent-mail 功能形态待 §7 决策

## 七、待确认事项

1. 现有四只原生积木（vault / cabinet / ppt-studio / agent-mail）是否拆为独立小程序包、从底座移出（出厂 app 零积木），还是保留内置只作首期示范？——用户此前倾向"内置也逐步拆出"，待最终确认。
2. 第一只端到端示范积木选哪只（建议选 vault 或做一个新轻量积木跑通下载-安装-打开-卸载全链路）。
3. 产品积木包构建方式：本地 Xcode 工程 + 发布脚本产出 zip（不引入 CI，先手动发布）。
*（内容由AI生成，仅供参考）*
