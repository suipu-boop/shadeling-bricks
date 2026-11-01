# 契约 v1.0 离线断言取证台账 · 2026-11-01

> 由 Hermes（小白）在 2026-11-01 写入，交接 M4「小程序两只真机契约断言取证」的离线前置部分。
> 位置：`scripts/contract_assert.py`（可复跑断言脚本）+ 本文档（取证记录）。

---

## 一、目的

交接判据要求对 `vault` / `wechat-mp` 两只 product 做**契约 v1.0 断言取证**。
真机目视取证（装包 / 交互 / 硬信号 / CGEvent）属 owner 专属耗时项（需真机
Shadeling 运行 + 装机），本会话无法执行。故先把**离线可断言的契约面**固化为
可复跑脚本，作为真机前的**前置通过凭证**，并暴露契约与实现的真实偏差。

断言面（契约 `specs/Shadeling积木声明式UI架构设计与契约-v1.0.md`）：
- A. §2.5 UI 词表 —— UI 文档包裹形态 / 节点类型 / 事件 / props / 令牌表（复用 `verify_ui_doc.py` 同源规则，零双规则漂移）
- B. §3 manifest v2 —— schema / kind / ui.engine / logic.protocol / 必填字段
- C. §5.2 权限清单 —— permissions ⊆ 已知枚举；高危权限须有风险标注
- D. §3.3 quota —— 配额区间钳制

## 二、复跑方法

```bash
cd ~/Dev/brick-vault
python3 scripts/contract_assert.py            # 全部 product
python3 scripts/contract_assert.py vault      # 单只
```

退出码：0 全部 PASS；1 存在 FAIL（每票列出证据）。每次发布改版后复跑防回归。

## 三、2026-11-01 实测结果

| product | A1 UI词表 | B1 manifest | C1 权限 | D1 quota | 结论 |
|---|---|---|---|---|---|
| `wechat-mp` 1.2.1 | PASS | PASS | PASS（高危 agent.web.write 已标注） | PASS | **契约合规 ✓** |
| `vault` 2.0.0 | PASS | PASS | **FAIL** | PASS | 见下 |

### vault 2.0.0 的 C1 FAIL（真实契约-实现偏差）

`agent.text.write` **不在契约 §5.2 已知权限枚举**（桥权限 + UI 侧权限 + app 级 `network` 均无此名）。

- **事实**：vault 2.0 manifest.permissions = `[fs.pick, ocr.recognize, agent.text.write, ui.clipboard.write, notify]`。
- **契约**：§5.2 权限清单全文无 `agent.text.write`；§5.1「未知权限名 → 安装器拒绝安装（不静默忽略）」。
- **含义**：vault 2.0.0 声称使用 `agent.text.write`（规格 §7.2「AI 抽清单」走 `brick_agent_run`），但契约 v1.0 未登记该能力。装机时安装器 `BrickInstallGate` 会对未知 `agent.*` 拒装（TODO E2 已注释「未知 agent.* 会被安装期闸门拒装」）。
- **性质**：vault 2.0.0 是**未收口的在途工作**（marvis/b2-contract 分支未提交修改，规格文档「待老板拍板 3 项」），本台账**不代为改动**，仅如实暴露。
- **归口建议**：若 vault 2.0 需要 `agent.text.write`，须**先升版契约 v1.0 登记该权限**（列风险级别 / 逐能力 I/O / 底座落地清单），否则装机即拒。此项归 owner + Marvis 拍板。

## 四、给接手者 / owner 的接续指引

1. **真机目视取证**（未做，属 owner）：安装 wechat-mp 1.2.1 + vault 2.0.0 到真机 Shadeling，硬信号断言契约 §4（握手 / ui/update 首帧 / 事件上行 / 卸载回收）。此为该判据的**真机侧**，本会话未具备条件。
2. **vault 2.0.0 契约缺口**：`agent.text.write` 未登记，拍板升版契约或移除该权限（见 §三）。
3. 本脚本**未挂入 verify_all.sh**（避免把 vault 2.0 的 in-flight 缺口变成阻断闸门红掉 Marvis 现有流程）；确需纳入发布闸门时由 owner 拍板后再接入。

## 五、红线遵守

- 分支 `hermes/m4-contract-assert` 基于 marvis/b2-contract HEAD 新建，仅提交本会话新增的 `contract_assert.py` + 本台账，**未改动任何被跟踪的他人未提交文件**（vault 2.0 源码 / manifest / 规格等原地保留）。