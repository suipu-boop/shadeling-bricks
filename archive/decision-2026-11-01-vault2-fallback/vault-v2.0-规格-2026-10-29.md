---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_689a4157d39211f19101525400de85a5
    ReservedCode1: og6A0ea0J/dFgHMtQSwpjGXcGmc9rJexNtuUnNKRA/2EJgzgvT53JQaRVdx6XiWIkoHeT1YfyoFNidnGNrDyTVzlvH8EGoXfrUrtvxlyzLDzXJqdFiNGG6MfnVQ4Z/VDFKWdQMbnhBAMLsUf2qXCf402Mf5x4pSMyIeGgQaz3rKd7MgmDoBvI3Jf1VE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_689a4157d39211f19101525400de85a5
    ReservedCode2: og6A0ea0J/dFgHMtQSwpjGXcGmc9rJexNtuUnNKRA/2EJgzgvT53JQaRVdx6XiWIkoHeT1YfyoFNidnGNrDyTVzlvH8EGoXfrUrtvxlyzLDzXJqdFiNGG6MfnVQ4Z/VDFKWdQMbnhBAMLsUf2qXCf402Mf5x4pSMyIeGgQaz3rKd7MgmDoBvI3Jf1VE=
---

# vault v2.0 规格 · 材料台账

> 日期：2026-10-29
> 状态：待老板拍板（3 项，见 §11）
> 取代：vault 1.x「本地资产中枢」（v1 独立应用 + 1.2.x 小程序，均为泛化资产存储）

---

## 1. 一句话定位

**不存"东西"，管"要交的东西"。** 倒计时告诉我哪天要交、清单告诉我还缺什么、打包按钮帮我把材料交出去。

1.x 的问题不是技术，是没有"派上用场的时刻"——打开它只能看到一堆资产，看完就关。2.0 只为三个时刻存在：

| 时刻 | 谁触发 | 2.0 做什么 |
|---|---|---|
| 领导/协会发来申报通知 | 外部 | 选一张通知截图 → 自动生成事项 + 材料清单 + 截止日 |
| 睡前想起"证是不是过期了" | 自己 | 打开即见临期红条，逾期项永远置顶 |
| 报送前一天 | 截止日 | 点「打包」→ 出 zip（清单.md + 附件分目录） |

---

## 2. 与 1.x 的根本差异

| 维度 | 1.x | 2.0 |
|---|---|---|
| 组织单位 | 单条资产（文件/图片/网页/笔记） | **事项**（一个事项含多条材料与多个附件） |
| 首屏 | 全部资产平铺 + 类型筛选 | **按紧迫度排序的待办台账** |
| 核心动作 | 存、查、OCR 识别 | **补齐、打包、结项** |
| 时间维度 | 无 | 倒计时 + 四级紧迫度 |
| AI | 总结摘要、打标签 | **从通知生成清单、查缺补漏** |
| 成功判据 | 存进去了 | **按时交出去了、没漏材料** |

旧 `assets` 表不删不改，2.0 只新增表，旧的作为"参考资料库"从二级入口进（见 §5.3）。

---

## 3. 信息架构

```
首页 · 台账
├─ 顶部：一句状态（"3 项待办 · 最近截止 5 天后"）
├─ 紧迫度统计（逾期 / 7 天内 / 30 天内）
├─ 检索 + 分类筛选
├─ 事项列表（按紧迫度→截止日升序）
└─ 底部动作：新建事项 / 从通知识别 / 刷新

事项详情（sheet）
├─ 标题、类别、层级、截止日、倒计时
├─ 完成率进度条（已备/应备）
├─ 材料清单（逐条：名称 · 状态 · 附件数 · 挂附件 · 切换状态）
└─ 底部：打包报送 / 标记完成 / 编辑 / 删除

新建·编辑（sheet）  → 标题/类别/层级/截止日/备注
从通知识别（sheet） → 选图 → OCR 文本 → AI 抽清单 → 勾选采纳 → 生成事项

归档（二级）→ 已完成 / 已归档事项 + 参考资料库（旧 assets）
```

---

## 4. 数据模型（`SHADELING_HOME/vault/vault.db`，新表）

```sql
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,        -- 申报|年检|评审|归档|其他
  level TEXT DEFAULT '',     -- 校级|厅级|协会|国家级|其他
  deadline TEXT DEFAULT '',  -- YYYY-MM-DD，空=无期限
  state TEXT NOT NULL DEFAULT 'active',  -- active|done|archived
  note TEXT DEFAULT '',
  source_path TEXT DEFAULT '',  -- 来源通知文件路径（可空）
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 1,   -- 1=必备 0=选备
  state TEXT NOT NULL DEFAULT 'missing', -- missing|have|checked
  note TEXT DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_files (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  material_id TEXT DEFAULT '',   -- 空=未归属材料
  name TEXT NOT NULL,
  path TEXT NOT NULL,            -- 归档副本绝对路径
  size INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT DEFAULT '',
  added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT DEFAULT ''
);
```

**归档副本策略**：`fs.pick` 选中的文件**复制**到 `SHADELING_HOME/vault/items/<item_id>/`，不移动原件；重名加 `-2` 后缀。原文件被删不影响台账，台账记录 sha256 便于查重。

### 4.1 紧迫度分级（纯函数，可单测）

```
d = deadline - today（天）
d < 0        → overdue  逾期 N 天
0 ≤ d ≤ 7    → urgent   剩 N 天
8 ≤ d ≤ 30   → soon     剩 N 天
d > 30       → later
deadline 空  → nodate   无期限
```

列表排序键：`(state=active 优先, 紧迫度序 overdue<urgent<soon<later<nodate, deadline 升序, updated_at 降序)`。

### 4.2 完成率

```
rate = (materials.state IN ('have','checked') 的条数) / 总条数
必备项未备 → 完成率显示为上限 99%，禁止显示 100%（防"看着齐了其实缺"）
```

---

## 5. 界面逐页（组件严格落在渲染器白名单内）

可用节点：`container / text / button / progress / list / card / form / overlay / image / icon / grid`。
可用事件：button.tap、list.select/tap（行内事件以 **list 节点 id + payload.index** 上抛）、card.tap/select/action、form.change/submit、overlay.confirm/cancel/primary/secondary。

### 5.1 首页

| 区块 | 组件 | 关键属性 |
|---|---|---|
| 标题 | text | `value={{state.headline}}`、`style=title` |
| 状态句 | text | `{{state.status_line}}`、`style=caption` |
| 统计 | grid | `columns=3`，内含 3 个 card（`icon` + `title`=数字 + `subtitle`=标签） |
| 检索 | form | `fields=[{field_id:q,kind:text,placeholder:"搜事项/材料"}]`、`submit_label=搜索` |
| 筛选 | container(horizontal) | 5 个 button：全部/逾期/7天内/30天内/无期限（选中态靠 `style` 切换） |
| 列表 | list | `items={{state.rows}}`、`selection=single`、`empty_state={{state.empty_hint}}`，唯一子节点为 card 模板 |
| 行模板 | card | `title={{row.title}}`、`subtitle={{row.deadline_line}}`、`meta={{row.progress_line}}`、`tags={{row.tags}}`、`badge={{row.badge}}`、`icon={{row.icon}}`、`actions=[{label:"详情",action:"open"}]` |
| 底部 | container(horizontal) | button：`新建事项` / `从通知识别` / `刷新` |
| 提示条 | overlay(kind=banner) | banner_info（level=info）、banner_warn（level=warn） |

### 5.2 事项详情（overlay kind=sheet，`width` 取默认）

- `text` 标题 + `text` meta（类别·层级·截止日·倒计时）
- `progress` `value={{state.detail.rate}}`、`label={{state.detail.progress_label}}`
- `list` 材料行（子节点 = `container(horizontal)`：`icon`（状态点）+ `text`（名称+备注）+ `text`（附件数）+ `button`（挂附件））
- 材料行点击 → 切换状态 missing→have→checked→missing
- 底部 `container(horizontal)`：`打包报送` / `标记完成` / `编辑` / `删除`
- 附件区：`list` 文件行（`image` 缩略图仅对 png/jpg 显示，其余用 `icon=doc`）

### 5.3 归档 & 参考资料库

`overlay(kind=sheet)`：两段——「已完成/已归档事项」（list）与「旧资产库」（list，只读，`empty_state="旧资产库为空"`）。

### 5.4 从通知识别（overlay kind=sheet）

`button`（选通知文件）→ `progress`（识别中）→ `text`（识别文本前 200 字，折叠）→ `list`（AI 抽出的清单行，带勾选）→ `button`（生成事项）。
识别失败：`overlay(banner, level=warn)` + 手动新建入口。

---

## 6. 界面状态快照（`state_snapshot` 必须全量声明）

```
q, filter, headline, status_line, empty_hint,
stat_overdue, stat_urgent, stat_active,
rows[], row_count, truncated, banner, banner_is_info, banner_is_warn, last_action_line,
detail_open, detail_id, detail_title, detail_meta, detail_rate, detail_progress_line, materials[], detail_files[], detail_can_pack,
sheet_open, sheet_mode, sheet_title, sheet_error,
import_open, import_stage, import_text, import_rows[], import_error,
archive_open, archived_rows[], legacy_rows[],
confirm_kind, confirm_open
```

每个 `if` 分支字段必须在快照里声明初值，否则首帧校验失败（4304）。

---

## 7. 关键能力实现

### 7.1 打包报送（核心交付动作）

```
目标目录 = fs.pick(directory)
输出：{title}_{YYYYMMDD}.zip
内含：
  清单.md          —— 事项信息 + 材料表（名称/状态/附件数）+ 缺失项汇总
  {序号}_{材料名}/ —— 该材料下的附件原件（无附件则建空目录 + 缺项标记）
  未归类/          —— material_id 为空的附件
缺项处理：缺失的必备材料在清单.md 顶部「⚠ 缺失 N 项」列出，不阻断打包
```

### 7.2 从通知识别

1. `fs.pick` 选中图片/PDF → `ocr.recognize` 取文本
2. 走 `brick_agent_run`（权限 `agent.text.write`），提示词要求**只输出 JSON**：
   `{title, kind, level, deadline, materials:[{name, required}]}`
3. 解析失败 → 降级为"手动填标题 + 空清单"，不清空用户已输内容
4. 用户勾选采纳的清单行 → 生成 items + materials
5. **AI 不可用**（未授权/超时）→ 整个 sheet 隐藏识别按钮，只留手动路径（优雅降级，不报错）

### 7.3 启动扫描

冷启动时执行：逾期/7天内条目置顶 + `banner_warn` 一句"逾期 2 项、7 天内 1 项"。不弹系统通知（底座未提供通知能力，避免伪造）。

---

## 8. 权限（manifest）

| 权限 | 用途 | 缺失时 |
|---|---|---|
| `fs.pick` | 选附件、选通知文件、选打包目录 | 不可用附件与打包，台账仍可手工维护 |
| `ocr.recognize` | 识别通知文件 | 隐藏「从通知识别」入口 |
| `agent.text.write` | 抽清单 | 同上，降级手动 |
| `fs.write` | 写归档副本与 zip | 同上 |

`auth.biometric` **移除**：2.0 不再有"敏感字段加密"场景（证件号不再往库里抄，附件原样归档更安全）。父类权限按 manifest 继承规则声明。

---

## 9. 验收标准（`tests/selftest_vault.py`，全绿才算完）

- [ ] 紧迫度边界：d = -1/0/7/8/30/31/空 → overdue/urgent/urgent/soon/soon/later/nodate
- [ ] 排序：逾期项永远在 7 天内侧之前；已完成项不进 active 列表
- [ ] 完成率：全备 → 100%；必备缺 1 → 显示 ≤99%
- [ ] 材料状态循环 missing→have→checked→missing 三态闭环
- [ ] 删事项级联删 materials 与 item_files，磁盘归档目录一并清理
- [ ] 重名附件不覆盖，落 `-2` 后缀
- [ ] 打包产物：zip 可解、含清单.md、附件按材料分目录、缺项在清单顶部
- [ ] 识别路径：mock OCR + mock agent 返回合法 JSON → 生成 1 事项 N 材料；返回脏文本 → 降级不崩
- [ ] AI 不可用：`import` 入口隐藏，手动新建正常
- [ ] 首帧 `ui/update` 通过 `validateUIDocument`，无 4303/4304
- [ ] 空库首帧：不崩、显示空态文案

---

## 10. 实施顺序

| 步 | 内容 | 产出 |
|---|---|---|
| T1 | 数据层：建表、items/materials/files 增删改查、紧迫度纯函数 | `logic/store.py` + 单测 |
| T2 | UI 文档：首页 + 4 个 sheet + 2 个 banner | `ui/main.json`（约 900 行） |
| T3 | 逻辑层：事件路由、三态流转、归档复制、打包 zip、识别链路 | `logic/vault` |
| T4 | 自测全绿 → `package_brick.sh` → 1.3.0 实包 → index.json 登记 → 真装验收 | `releases/1.3.0/` |

**版本号**：定位全换但 manifest name 不变 → 记 `1.3.0`（避免与旧 2.x 编号冲突；若要叫 2.0.0 我改一个字即可）。

---

## 11. 待老板拍板（3 项，一句话即可）

1. **定位**：就按"材料台账（申报/年检/评审的清单与截止日）"，还是你要的是别的（例如纯证照到期、或教学档案）？
2. **AI 识别建事项**：要不要（涉及 ocr + agent 权限，做起来多 1 步）？砍掉则只剩手动录。
3. **旧数据**：1.x 那批 assets 保留为只读"参考资料库"入口，还是 2.0 直接不带它们？
*（内容由AI生成，仅供参考）*
