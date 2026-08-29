# brick-vault 冻结说明（FROZEN）

> 依据：`brickery/specs/m1-product-line-slim.md` 第三节冻结清单（M1 产品线瘦身，2026-08-29 拍板执行）
> 范围：`bricks/` 下全部 22 个积木目录
> 原则：**只冻结不删除**，任何积木目录不得被移除。

## 冻结清单（22 个积木分类）

| 分类 | 积木 | 后续处理 |
|---|---|---|
| 保留活跃 | ppt-studio、vault | 原生 UI 积木，M4 原生重写 |
| 工具层保留 | docwrite | 进底座工具层（支撑 PPT 链路） |
| 冻结保留（不删） | high-config-doc、demo-studio | 内核实现保留；demo-studio 仅开发期验证工具 |
| 冻结归档（17 个） | ax / backup-restore / browser / code-quality-chain / doctor / engine-api / engine-local / feishu / hello-marvis / mcp / meeting-minutes / multi-agent / rules / scheduler / skill-library / telegram / visualize | 收进底座原生实现（M3 一次全收），vault 目录冻结不再维护 |

## 活跃清单（仅 3 个）

- `bricks/ppt-studio` — 保留活跃
- `bricks/vault` — 保留活跃
- `bricks/docwrite` — 工具层保留

## 维护约定

1. 冻结归档目录不得继续提交功能变更；如确需修改，须先在 specs 解冻并登记。
2. M3 底座原生实现完成前，冻结目录保留原样，供历史引用与迁移参考。
3. 本文件与 `skills/`（技能源）无关；技能目录以各自 index.json 为准。
