---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_bdcfafdb9dc911f1a65b525400826444
    ReservedCode1: tTUz6EF9MkBproMB9g9safy7CsNjaIzSS5SViX5t1NkZTk0DMKXXYP8TEi9VbXJtRnPHpTpgYAIM+xUKElFUjPSE0qoNh4QJ9uLB4dOFRj7YfpdIgw1/vP8NMAtgs8Ka5UwBJicbXBMupJM2dTq5Sjsckx7ugr63BfJrROXC20F1DbBx7cqLkFj5S2M=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_bdcfafdb9dc911f1a65b525400826444
    ReservedCode2: tTUz6EF9MkBproMB9g9safy7CsNjaIzSS5SViX5t1NkZTk0DMKXXYP8TEi9VbXJtRnPHpTpgYAIM+xUKElFUjPSE0qoNh4QJ9uLB4dOFRj7YfpdIgw1/vP8NMAtgs8Ka5UwBJicbXBMupJM2dTq5Sjsckx7ugr63BfJrROXC20F1DbBx7cqLkFj5S2M=
---

# 积木加工厂 App（Brick Factory App）设计

> 状态：**已迁出**（2026-08-22 工厂独立为 brickery-factory 仓库，本文档仅留档）
> 设计正文与实施记录已移至 [brickery-factory/specs/brick-factory-app.md](https://github.com/suipu-boop/brickery-factory/blob/main/specs/brick-factory-app.md)
> 本仓库（brick-vault / shadeling-bricks）现只保留：积木库本体（bricks/ + index.json）与验证闸门（scripts/verify_bricks.py）
> 关联：ARCHITECTURE.md（四项目全局）、brickery-factory/specs/（工厂设计权威版）
> 定位：工坊（Workbench）= 消费积木；加工厂（Factory）= 生产积木。本设计把加工厂做成**独立 app**，不是纯网页版。

## 一、用户拍板的方向

1. **独立 app**：与积木工坊同形态（Swift 壳 + 本地 server + web 前端），非纯网页版。
2. **产出即上传**：积木工作完成后直接上传到本仓库的 GitHub 库（brick-vault）。
3. **独立对话功能**：app 内置一个功能相对单一的 agent——**积木生产 agent**。用户用自然语言描述需求，agent 造出合规积木（brick.json + 实现文件）→ 自检 → 上传。

## 二、形态（对齐工坊）

参照 brickery-workbench（app/ Swift 壳 + brickery/web/ 后端 + web/ 前端 + build 脚本），工厂 app：

```
brick-vault/                        # 本仓库（积木加工厂）
├── factory/                        # 【新增】工厂后端（server.py + 对话 agent 装配）
├── web/                            # 【新增】工厂前端（index.html）
├── scripts/build_factory_app.sh    # 【新增】构建脚本（仿 build_workbench_app.sh）
├── specs/                          # 【新增】本目录（设计文档）
├── bricks/ index.json              # 既有：积木库本体（数据源）
└── skills/                         # 既有：市场技能源
```

- 后端：仅标准库 http.server（对齐工坊 server.py 风格），端口 **8767**。
- 前端：工厂蓝图风（复用/参考工坊 web/index.html）。
- Swift 壳：**复用共享 app/ 壳**（brickery-workbench/app 与 brickery/app 同源，双仓库同步约束），通过 Info.plist CFBundleIdentifier 区分运行模式（工坊 detectRunMode 机制已支持扩展）。
- 内嵌 python 与构建流程：仿 build_workbench_app.sh（内核来自 brickery GitHub，合并工厂覆盖）。

## 三、核心功能

**权威源 = GitHub 积木库（shadeling-bricks）**：brick-vault 本地仓库的 origin 即
`https://github.com/suipu-boop/shadeling-bricks.git`，与工坊 live_vault 同源。
工厂以 GitHub 为权威，本地只有工作副本，**能读、能修、能改、能回传**。

| 功能 | 说明 |
|------|------|
| GitHub 实时同步（读） | 启动/手动刷新时从 GitHub clone/pull 最新积木库到本地工作副本（`~/.brickery/factory-vault`，仿 live_vault，可随时重建）；对话 agent 操作前自动 pull |
| 积木清单 | 浏览 GitHub 库全部积木（index.json + 各 brick.json），实时反映远端状态 |
| 积木编辑器 | 新建/编辑 brick.json 5 字段 + 元数据，管理实现文件；修改工作副本中的积木 |
| 验证闸门 | 发布前强制自检：schema 校验 / 依赖冲突完整性 / 资源文件存在性 / 按钮与内核 handler 对齐。**不过闸门不允许发布** |
| 对话生产 | 独立对话窗口，内置积木生产 agent，自然语言 → 造积木 |
| 修改/修复（写回） | 对已有积木修改后，同样过闸门 → push 回 GitHub，工坊实时可见 |
| 发布上传 | 自检通过 → push 到 GitHub（shadeling-bricks），并提示工坊侧 live_vault 刷新 |

## 四、积木生产 agent（独立对话功能）

- **职责单一**：只做积木生产闭环——理解需求 → 生成 brick.json + 实现文件（PromptBrick/ServiceBrick/ConnectorBrick 三类模板）→ 登记 index.json → 自检 → 准备上传。
- **内核复用**：对话能力复用 brickery 内核（loop/supervisor/ipc），工厂后端以 `python -m brickery...` 方式运行，或按内核提供的最小装配入口挂载。
- **能力边界**：不处理与积木生产无关的对话；遇到契约不清/高风险改动（删积木、破坏性变更）停下问用户。
- **上传前确认**：push 前展示本次变更摘要（新增/修改的积木、index.json diff），用户确认后执行 push（遵守"push 前明确确认"约定；用户可后续改为免确认）。

### 4.1 Agent 的 LLM API 输入（参考底座）

积木生产 agent 需要 LLM 才能对话，**完全复用底座（工坊产出 agent）的 API 输入机制**，不另造轮子：

| 机制 | 底座实现 | 工厂复用方式 |
|------|----------|--------------|
| 引擎配置模型 | `brickery/runtime/config.py::EngineConfig`（api_url / api_key / api_model，仅显式填写时非空） | 直接复用，工厂后端读同一配置 |
| API 引擎 | `engine_providers.py` ApiEngine（OpenAI 兼容 /chat/completions） | 复用 EngineProviderRegistry 构建 |
| 引擎积木 | `bricks/engine-api`（engine_kind=api，不携带端点/密钥） | 工厂 app 装配时挂 engine-api 积木 |
| 未配置即不可用 | api_url/api_key 未填 → is_available=False | 对话前检测，未配置则引导去设置页填写 |
| 安全红线 | 端点/密钥由用户显式填写，key 存 `~/.brickery/config/`，不进 git、不进记忆库；前端掩码显示、空 key 不覆盖已存值 | 完全沿用 |

**首次使用流程**：工厂 app 启动/首次对话 → 检测到未配置 API → 打开设置页（对齐底座 setup_wizard 交互）引导填写 api_url / api_key / api_model → 保存到 EngineConfig → 之后对话直接可用。配置变更仅影响本机，不随积木上传 GitHub。

## 五、关键流程

```
GitHub(shadeling-bricks) ──启动/刷新 clone・pull──▶ 本地工作副本(~/.brickery/factory-vault)
   ▲                                                      │
   │                                                      ▼
   └── push ◀── 用户确认 ◀── 变更摘要 ◀── 验证闸门 ◀── 对话 agent 造/改积木
```

- 读：启动/手动刷新 → 从 GitHub 拉最新；对话 agent 每次操作前自动 pull（防基于过期副本修改）。
- 写：造/改积木 → 验证闸门自检（失败回炉）→ 展示变更摘要 → 用户确认 → push 回 GitHub。
- 冲突：push 前再次 pull，遇冲突停下提示用户手动处理。

## 六、验证闸门（地基）

发布前强制自检，等价内核 `make verify`：
1. brick.json schema 校验（5 字段契约 + 元数据）
2. dependencies 依赖/冲突声明完整性
3. files 资源文件存在性（src 相对积木目录必须存在）
4. 按钮/能力与内核 handler 对齐（若有按钮类积木）
5. index.json 登记一致（name/version/category/risk_level/summary/path 与 brick.json 对齐）

闸门脚本：`scripts/verify_bricks.py`（内核已有，工厂复用/对齐）。

## 七、契约与同步约束

- 工厂产出必须严格过 brick.json 5 字段契约（specs/brick-schema.md，权威在内核 skill_library.py）。
- **契约变更需通知工坊侧**（brickery-workbench live_vault 直连本仓库 skills/index.json + bricks/）。
- app/ 壳为双仓库共享组件，改动需同步 brickery-workbench/app 与 brickery/app，禁止单边修改。
- 内核单权威在 brickery 仓库；工厂后端尽量零内核依赖（除对话 agent 必需的运行时）。

## 八、实施顺序

1. **地基**：验证闸门（scripts/verify_bricks.py 落地/对齐）+ specs 契约文档确认
2. **后端骨架**：factory/server.py（清单 API + 验证 API），端口 8767
3. **前端**：web/index.html（清单 + 编辑器 + 验证结果展示）
4. **对话 agent**：积木生产 agent 装配（复用内核），对话式造积木
5. **发布上传**：git commit + push GitHub + 通知工坊侧
6. **打包**：build_factory_app.sh → .app + .dmg（复用共享 Swift 壳）

## 九、待拍板清单

1. **同步时机**："实时"粒度——启动自动同步 + 手动刷新按钮（推荐）？还是加定时轮询？
2. **push 确认**：默认"变更摘要 → 用户确认 → push"（推荐，遵您 push 前确认的约定），还是做成免确认一键直接上传？可做成可配置。
3. **GitHub 凭据**：push 认证复用系统 git 凭据（macOS keychain / SSH，推荐，不造新认证），还是工厂 app 内填 token？
4. **破坏性操作边界**：删除积木 / 覆盖已发布积木（影响工坊使用者）需二次确认（推荐）；普通新增/修改走正常闸门。
5. **工厂代码归属**：工厂后端+前端代码放 brick-vault 仓库（push 积木时可选带/不带），还是独立仓库（如 brickery-factory）？（参考工坊为独立仓库 brickery-workbench）
6. **对话 agent 装配**：复用内核运行时、独立装配（不依赖工坊 produce 链路），是否认可？
7. **契约变更通知工坊侧**：固化流程——契约（brick-schema）变更时需同步通知工坊侧适配，通知方式（会话提示/文档变更记录）？
*（内容由AI生成，仅供参考）*

## 十、已拍板决策记录

| 日期 | 决策项 | 结论 |
|------|--------|------|
| 2026-08-22 | 5. 工厂代码归属 | **独立仓库**：新建 `brickery-factory`，factory/ + web/ + build_factory_app.sh + app/ 壳迁入；brick-vault 只留积木与验证闸门。类比工坊 brickery-workbench 独立形态，职责分离不污染产品库历史 |
| 2026-08-22 | 3. GitHub 凭据 | **复用本机 git 凭据**（SSH key / credential helper），零新增存储，不造 token 方案 |
| 2026-08-22 | 6. 对话 agent 装配 | **复用内核运行时独立装配**（工厂内置单一职责对话 agent，不依赖工坊 produce 链路） |
