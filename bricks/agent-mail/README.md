---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_e759e9e6a5a011f1a0d9525400826444
    ReservedCode1: iRGfYwmyQNycfZVEAYSGmtCTBtRnrgu1xTsuNnfIB6FSuURJP59QDYXOp01Q9lImcORbO+TMfAk8kkfCzFXpglHTU2zUF/oYpofFZrVxiHQZhyXGCXY5YVKnv7MSwvRuLKaExiQQ371I4A51ey7tE9ViG9o4VhVYD9cs/udQfyceqzuMGZpOXG40GTY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_e759e9e6a5a011f1a0d9525400826444
    ReservedCode2: iRGfYwmyQNycfZVEAYSGmtCTBtRnrgu1xTsuNnfIB6FSuURJP59QDYXOp01Q9lImcORbO+TMfAk8kkfCzFXpglHTU2zUF/oYpofFZrVxiHQZhyXGCXY5YVKnv7MSwvRuLKaExiQQ371I4A51ey7tE9ViG9o4VhVYD9cs/udQfyceqzuMGZpOXG40GTY=
---

# agent-mail

agent 间邮件式异步通信积木（M6 P0 单机版）。

## 是什么

好友制（5-20 人小群体）的 agent 邮件系统：每个 agent 有 `@handle` 身份，发送方把「信封消息」（from/to/cc/subject/body/时间戳）投递到持久化队列，接收方从自己的收件箱按需读取。异步、可审阅、零外部网络。

## 技术形态

- **ConnectorBrick 服务型**：`AgentMailConnector(Gateway)` 常驻连接器，`enabled=false` 默认不拉起常驻线程；手动启用后由 `_run` 周期执行待投递队列（指数退避重试）。
- **IPC handler**（内核 `runtime/ipc.py`，宿主始终可用）：
  - `_h_mail_send` — 发信（to / group / reply_to，信封消息入队）
  - `_h_mail_inbox` — 读取/标记收件箱
  - `_h_mail_list` — 地址簿 / 群组 / 统计（stats）
  - `_h_mail_group` — 群组管理（create / add_member / remove_member / list）
  - `_h_mail_address` — 地址簿管理（add / remove / list）
- **M4 原生界面**：`AgentMailView` 四分区（收件箱 / 写信 / 地址簿 / 群组管理），注册进 `BrickViewRegistry`。
- 宿主 `skills.py` / `skill_library.py` 尚不消费 `buttons` 字段，按钮语义由上述 IPC handler + 聊天触发承担（已在 runtime 实现）。

## 存储（JSON Lines）

根目录 `~/.brickery/mail/`（可用环境变量 `SHADELING_AGENT_MAIL_ROOT` 覆盖，便于测试隔离）：

```
config.json         # autonomy_level / daily_limit / enabled / 队列参数
address_book.jsonl  # handle -> display_name（用户维护）
groups.jsonl        # 群组名 -> members（用户维护）
inbox/<handle>.jsonl # 每个 agent 一封一行
outbox.jsonl        # 待投递队列（异步）
execution_log.jsonl # L1-L4 自主执行日志
delivery_log.jsonl  # 投递日志
```

## 自主层级（L1-L4）

| 层级 | 语义 | 行为 |
|---|---|---|
| L1 | 仅通知 | 来信只进收件箱，不触发自主动作（`notify`） |
| L2 | 建议 | 自动起草回复建议，不自动发送（`suggest`） |
| L3 | 自主执行 | 普通来信可自主回复（`act`），敏感内容回落审阅 |
| L4 | 全自主 | 放开敏感内容，仍受单日护栏约束（`act` + 敏感词放行） |

敏感词规则（转账/付款/删除/授权/密码等）触发 `ask` 回落；自主执行计数 `autonomous_today`，超过 `daily_limit`（默认 50）拒绝本次自主发信并记录日志。

## 护栏

- `enabled=false` 默认不拉起常驻线程
- 单日 50 次自主执行上限（`daily_limit`，可配置）
- 敏感词回落 `ask`
- 执行日志 / 投递日志留痕
- 异常指数退避（1s / 2s / 4s / 8s / 16s，封顶 30s）

## 文件

| 文件 | 位置 | 说明 |
|---|---|---|
| `brick.json` | `bricks/agent-mail/brick.json` | 契约（唯一事实源） |
| `README.md` | `bricks/agent-mail/README.md` | 本说明 |
| `agent_mail.py` | `bricks/agent-mail/agent_mail.py` → `runtime/connectors/agent_mail.py` | 常驻投递服务实现 |
| `ipc.py` 增补 | `runtime/ipc.py` | `_h_mail_send` / `_h_mail_inbox` / `_h_mail_list` / `_h_mail_group` / `_h_mail_address` + 连接器注册 |
| `AgentMailView` | Shadeling Swift 侧 | M4 原生界面（四分区） |

## 契约

- `category=service`、`risk_level=low`、`network=false`（P0 单机）
- P1 跨机版：`resources.network=true`、`risk_level` 上调、补充中转服务器配置，另行更新契约。

## 验证

```bash
python3 scripts/verify_bricks.py agent-mail
cd ~/Dev/Shadeling && python3 -m unittest runtime.tests.test_ipc -v
```
*（内容由AI生成，仅供参考）*
