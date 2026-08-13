# Brick Vault（积木库）

> Shadeling 积木的独立仓库，与内核仓库（`/Users/suipu/Dev/Shadeling`）物理分离。

## 定位

- 内核仓库只留 `supervisor / loop / engine_router / ipc` + 积木宿主，不持有具体积木。
- 本仓库承载所有「四肢」积木：连接器、技能、安全、文档、工具等。
- 内核与本仓库之间唯一接口是 brick 契约（`brick.json`），契约定义见积木平台 `specs/brick-schema.md`。

## 结构

```
brick-vault/
├── bricks/          # 每个积木一个子目录
│   ├── feishu/      # 连接器积木（P1）
│   │   ├── brick.json
│   │   └── ...
│   └── ...
├── index.json       # 积木清单（工厂/画布读这个）
└── README.md
```

## 契约

每个积木必须自带 `brick.json`，5 字段（capabilities / dependencies / resources / risk_level / composition）遵循积木平台 `specs/brick-schema.md`。任何 brick.json 改动须过 `make verify` 闸门。

## 恢复约定

继续积木平台的工作前，先读积木平台 `docs/ROADMAP.md` 对齐当前阶段（当前：P0 已完成，P1 提取试点）。

## 将来发布

本仓库为本地 git 仓库，将来可直接 push 到 GitHub 作为公开/私有积木库；Shadeling 的积木市场（skill_library）可指向它作为源仓库。
