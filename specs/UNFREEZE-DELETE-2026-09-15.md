---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_ee9fd378b10911f188ac525400dcc5b3
    ReservedCode1: k+EBcaU2jAv1gDE6vcz6539HjNeNRqwTsUHxPY4GlNAtutInkBXO7NQNlXCe7E0HDsRL/+8dLw8oEpN7zGF35kZtXaFsNq62aWyMuEeJL3YKVd3R4N2m0aChAQgAXMKlAToN3LblPvuoZQ9XJRLCoZZwUU9ATumKuO5O19puGPDuAZfbVRLZUKcuzzQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_ee9fd378b10911f188ac525400dcc5b3
    ReservedCode2: k+EBcaU2jAv1gDE6vcz6539HjNeNRqwTsUHxPY4GlNAtutInkBXO7NQNlXCe7E0HDsRL/+8dLw8oEpN7zGF35kZtXaFsNq62aWyMuEeJL3YKVd3R4N2m0aChAQgAXMKlAToN3LblPvuoZQ9XJRLCoZZwUU9ATumKuO5O19puGPDuAZfbVRLZUKcuzzQ=
---

# brick-vault 解冻删除登记（2026-09-15）

> 状态：已登记，删除已执行（工作副本）
> 依据：用户明确授权（2026-09-15）；本仓 `FROZEN.md` 维护约定第 1 条「如确需修改，须先在 specs 解冻并登记」；底座覆盖核查结论（17 个冻结归档积木功能已由 Shadeling 底座原生实现）

## 一、解冻删除清单（17 个冻结归档积木）

以下 17 个积木目录自本登记日起解冻，并从 `bricks/` 移除（git 层面删除），同步从 `index.json` 移除登记：

| # | 积木 | 原冻结分类 | 底座覆盖依据 |
|---|---|---|---|
| 1 | ax | 冻结归档 | Shadeling `builtin_skills/ax/skill.json`（内置技能） |
| 2 | backup-restore | 冻结归档 | Shadeling `runtime/ipc.py`（backup_default/export/list/restore） |
| 3 | browser | 冻结归档 | Shadeling `builtin_skills/browser/skill.json`（内置技能） |
| 4 | code-quality-chain | 冻结归档 | Shadeling 设置区对话工具开关组（m3-native-base-features.md B3.3） |
| 5 | doctor | 冻结归档 | Shadeling `app/.../DoctorView.swift` + `runtime/ipc.py`（doctor） |
| 6 | engine-api | 冻结归档 | Shadeling `runtime/engine_providers.py` / `engine_router.py` + `ipc.py`（models_*） |
| 7 | engine-local | 冻结归档 | Shadeling 引擎路由 + `ipc.py`（model_download_*） |
| 8 | feishu | 冻结归档 | Shadeling `runtime/connectors/feishu.py` + `ipc.py`（feishu_setup） |
| 9 | hello-marvis | 冻结归档 | Shadeling 设置区对话工具开关组（m3-native-base-features.md B3.3） |
| 10 | mcp | 冻结归档 | Shadeling `runtime/mcp.py` + `ipc.py`（mcp_list） |
| 11 | meeting-minutes | 冻结归档 | 技能形态独立存在于 `skills/meeting-minutes/`（与 bricks/ 目录无依赖） |
| 12 | multi-agent | 冻结归档 | Shadeling `runtime/ipc.py`（task_* / spawn） |
| 13 | rules | 冻结归档 | Shadeling `runtime/rules.py` + `ipc.py`（rules_*） |
| 14 | scheduler | 冻结归档 | Shadeling `runtime/scheduler.py` + `ipc.py`（task_*） |
| 15 | skill-library | 冻结归档 | Shadeling `runtime/skill_library.py` + `ipc.py`（skill_library_*） |
| 16 | telegram | 冻结归档 | Shadeling `runtime/connectors/telegram.py` + `ipc.py`（telegram_setup） |
| 17 | visualize | 冻结归档 | Shadeling `builtin_skills/visualize/skill.json`（内置技能） |

## 二、保留清单（不删除）

以下积木维持冻结/活跃状态不变：

- `bricks/ppt-studio` — 保留活跃（M4 原生重写中）
- `bricks/vault` — 保留活跃（V2 产品化进行中）
- `bricks/docwrite` — 工具层保留（支撑 PPT 链路）
- `bricks/high-config-doc` — 冻结保留（内核实现保留）
- `bricks/demo-studio` — 冻结保留（开发期验证工具，无底座覆盖）
- `bricks/agent-mail` — 活跃新增（不在 FROZEN.md 冻结清单内）

## 三、执行范围

- 仅限 brick-vault 仓库工作副本修改；不执行 git commit/push。
- `bricks/` 下 17 个目录删除 + `index.json` 移除对应登记（刷新 updated_at）。
- 文档引用仅清理明确指向被删目录的引用，不改动功能相关描述文字。
*（内容由AI生成，仅供参考）*
