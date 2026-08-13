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

每个积木必须自带 `brick.json`，5 字段（capabilities / dependencies / resources / risk_level / composition）。契约权威实现在内核仓库 `runtime/skill_library.py`（`validate_skill_package` / `_normalize_brick_fields`），本仓库 `scripts/new_brick.py` 内置镜像校验；提交前须过内核 `make verify` 闸门。

## 积木工厂（P3）

一条命令造合规积木：

```bash
python3 scripts/new_brick.py translator \
  --summary "中英互译，走本地模型" \
  --category skill --risk low \
  --capabilities "text.translate,text.zh2en,text.en2zh"
```

生成 `bricks/<name>/brick.json` + `README.md`，登记进 `index.json`，并自检 5 字段契约。

## 恢复约定

积木平台当前阶段：P0（契约）✅ → P1（首批 4 积木）✅ → P2（内核瘦身契约）✅ → P3（积木工厂）✅。

## 将来发布

本仓库为本地 git 仓库，将来可直接 push 到 GitHub 作为公开/私有积木库；Shadeling 的积木市场（skill_library）可指向它作为源仓库。
