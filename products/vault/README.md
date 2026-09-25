---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_da3bab51b81b11f1a526525400cd780f
    ReservedCode1: o8KTdk0B1fAa6vtD4or8AvzsfzyLnqz27pPaGKSiVFboCf+oGeEbV0zetsVBbTQaJj7L4L1sNJszZhqZ0PXph8ceG+FybLQr9sOy0zxFcA9u5FsGrqM+8wg29V1ol/DE+F0kL2TKbsrpR4qLf+5CHVVHVp6J8Rw6qtJW2vf3tIjM15zCvyBdRM0FIPE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_da3bab51b81b11f1a526525400cd780f
    ReservedCode2: o8KTdk0B1fAa6vtD4or8AvzsfzyLnqz27pPaGKSiVFboCf+oGeEbV0zetsVBbTQaJj7L4L1sNJszZhqZ0PXph8ceG+FybLQr9sOy0zxFcA9u5FsGrqM+8wg29V1ol/DE+F0kL2TKbsrpR4qLf+5CHVVHVp6J8Rw6qtJW2vf3tIjM15zCvyBdRM0FIPE=
---

# 本地资产中枢（vault）

Shadeling 产品型积木（`kind: product`，V2 小程序包）。

把底座 `runtime/vault_store.py` 的资产库搬到原生 macOS 前端：**证件 / 图片 / 网页收藏 /
笔记 / 技能快照**的归档、检索、详情查看与证件 OCR 识别，全部本地完成。

- 积木 id：`com.shadeling.brick.vault`
- 版本：`1.0.0`
- 入口 bundle：`Vault.app`
- 网络权限：无（`permissions: []`，全本地、不联网）

> 本积木以独立应用形态运行（独立窗口），由 Shadeling 作为聚合底座管理启动 / 卸载，不经过内核 IPC。

---

## 1. 目录结构

```
products/vault/
├── manifest.json                    # 积木清单（brick-app/v1 契约）
├── icon.png                         # 图标（1024×1024）
├── README.md                        # 本文件
├── .gitignore                       # 忽略 .build/ 构建缓存与打包中间产物
├── source/                          # SwiftPM 源码（macOS 14.0+）
│   ├── Package.swift
│   ├── Info.plist                   # 打包 .app 用的模板（复制进 .app/Contents/）
│   ├── package_app.sh               # 构建 → 组装 .app → 打 zip（含 manifest.json）→ 回填 sha256
│   └── Sources/Vault/
│       ├── VaultApp.swift           # @main 应用入口
│       ├── ContentView.swift        # 主界面：命令栏 + 类型筛选 + 卡片墙
│       ├── ManualAddSheet.swift     # 手动录入弹层
│       ├── DetailSheet.swift        # 资产详情弹层
│       ├── VaultModels.swift        # 数据模型（对齐底座 VaultAssetItem / payload 结构）
│       ├── VaultStore.swift         # SQLite 存储引擎（与 runtime/vault_store.py 同源库）
│       ├── VaultOCR.swift           # 证件 OCR（Vision + PDFKit，纯本地）
│       └── DesignTokens.swift       # 视觉令牌（粉紫玻璃风）
└── releases/
    └── 1.0.0/
        ├── vault-1.0.0.zip
        └── vault-1.0.0.zip.sha256
```

---

## 2. 功能模块

| 模块 | 说明 |
|---|---|
| 资产墙 | 卡片墙展示全部资产，按类型筛选（证件 / 图片 / 收藏 / 技能 / 笔记 / AI 沉淀） |
| 检索 | 顶部命令栏关键词搜索，标题 / 摘要 / 标签多维匹配 |
| 手动录入 | 手动新增资产，写入与底座同构的 `assets` 表 |
| 详情 | 查看单条资产的完整字段、扩展键值、AI 沉淀摘要与要点 |
| 证件 OCR | 拖入图片 / PDF 首页，`Vision` 本地识别文本并尽力抽取证件字段（签发机关、有效期等） |
| 敏感字段 | 与底座一致：敏感字段以 `openssl aes-256-cbc + pbkdf2` 加密后存入 `payload.enc` |

---

## 3. 数据与安全

- **与底座同源库**：读写 `SHADELING_HOME/vault/vault.db`；`SHADELING_HOME` 缺省时回退
  `~/Library/Application Support/Shadeling/vault`，再回退 `~/.shadeling/vault`。
  表结构与 `runtime/vault_store.py` 严格对齐，**本积木不新建、不改动库结构**。
- **敏感字段加密**：key 优先取 macOS 钥匙串（`shadeling-vault/vault-key`），
  回退 `vault/.vault_key`（权限 `0600`）。
- **无网络访问**：`permissions: []`，OCR 走系统 `Vision` 框架，不上传任何内容。
- 源码与 `manifest.json` 均不含任何凭据。

---

## 4. 本地构建与打包

前置：macOS 14.0+、Xcode Command Line Tools（`swift --version` 可用）。

### 4.1 一条命令

```bash
cd products/vault/source
bash package_app.sh 1.0.0
```

脚本会依次完成：

1. `swift build -c release`
2. 组装 `dist/Vault.app`（`Contents/MacOS/Vault`、`Contents/Info.plist`、`Contents/Resources/icon.png`）
3. ad-hoc 签名
4. 暂存包内 `dist/manifest.json`（`scripts/pack_product.py stage`：只带身份字段）
5. 打包 `releases/1.0.0/vault-1.0.0.zip`（zip 根目录即 `Vault.app` + `manifest.json`）
6. `scripts/pack_product.py finalize`：计算 sha256 → 写 `vault-1.0.0.zip.sha256` → 自动回填 `manifest.json` 与 `index.json` 的 `products[]` → 复核 zip 内容

> **zip 内必须含 `manifest.json`**：安装器解压后要读包内 manifest 才能确认积木身份 / 入口 bundle / 权限声明，缺了会直接中止安装。`verify_products.py` 已把该条做成发布闸门。

### 4.2 手动等价步骤

```bash
cd products/vault/source
swift build -c release
mkdir -p dist/Vault.app/Contents/MacOS dist/Vault.app/Contents/Resources
cp .build/release/Vault dist/Vault.app/Contents/MacOS/
cp Info.plist dist/Vault.app/Contents/
cp ../icon.png dist/Vault.app/Contents/Resources/
python3 ../../scripts/pack_product.py stage --product vault --out dist/manifest.json
mkdir -p ../releases/1.0.0
cd dist && zip -r -X ../../releases/1.0.0/vault-1.0.0.zip Vault.app manifest.json
cd ../.. && python3 ../../scripts/pack_product.py finalize --product vault --version 1.0.0
```

---

## 5. sha256 回填与包内 manifest（重要）

当前 `manifest.json` 中已回填 `1.0.0` 的实算校验和：

```json
"sha256": "e4a1b7f2542f9ea1a1edd548a426cf3980569ab76fb0e8404dd5c0a1e30499dc"
```

该值（含 `index.json` `products[]` 中的同名条目）由出包脚本自动回填，**不再手工维护**。后续发布新版本时：

1. 执行 §4.1 一条命令：`scripts/pack_product.py finalize` 会算 sha256、写 `.sha256`、回填 `manifest.json` + `index.json`，并复核 zip 内含 `manifest.json`（缺则报错不出包）。
2. 运行产品闸门自检：

   ```bash
   python3 scripts/verify_products.py vault
   ```

   期望输出 `[OK] vault`（该闸门不在 CI 内，必须手动执行）。

> 包内 `manifest.json` **不含** `sha256` / `download_url`：二者是仓库侧发布元数据，且 zip 无法包含自身哈希（回填即失效）。安装器只读身份 / 权限字段，不依赖它们。

---

## 6. 与 V1 积木 `bricks/vault/` 的关系

| | `bricks/vault/`（V1 声明式） | `products/vault/`（V2 产品积木） |
|---|---|---|
| 形态 | 内核内 Python 积木，走 IPC | 独立编译的 `Vault.app`，独立进程 |
| 安装方式 | 随底座 / 冻结区 | 从 GitHub 真实下载 zip 安装 |
| 进市场 | 否 | 是（`index.json` → `products[]`） |

两者读写同一个 `vault.db`，可并存；V2 化完成后 V1 条目按市场 V2 契约逐步退役。

---

## 7. 状态

- [x] `manifest.json`（10 个必填字段齐全）
- [x] `source/` 源码（SwiftPM executableTarget，macOS 14.0，`swift build -c release` 通过）
- [x] `README.md`
- [x] `icon.png`
- [x] `releases/1.0.0/vault-1.0.0.zip`（内含 `manifest.json`）与 sha256 回填（sha256 = `e4a1b7f2542f9ea1a1edd548a426cf3980569ab76fb0e8404dd5c0a1e30499dc`）
- [x] `index.json` 登记（`products[]` 已追加同名条目）
*（内容由AI生成，仅供参考）*
