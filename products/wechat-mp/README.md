---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1ff3ab34626ddcd667748776b4e29487_8554e286b81911f1a351525400de85a5
    ReservedCode1: GkhPS8U+zQIw6Gx6D0PmfcWV7vOZoYmRSIFSTxRyU16UW9N0iAqR+YpEhVXaX69wkCDeFJufK9FbwbBLGJJP4cOYWPyIt385EZ0x9njDSByzU/GW705Jly8LXkyZ6BfnQCDRVHUBsb/ROIjhrflbqK8aYKr4Sn3C6Q8GGQaGg1IGexXmMt2W9KWsjgA=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1ff3ab34626ddcd667748776b4e29487_8554e286b81911f1a351525400de85a5
    ReservedCode2: GkhPS8U+zQIw6Gx6D0PmfcWV7vOZoYmRSIFSTxRyU16UW9N0iAqR+YpEhVXaX69wkCDeFJufK9FbwbBLGJJP4cOYWPyIt385EZ0x9njDSByzU/GW705Jly8LXkyZ6BfnQCDRVHUBsb/ROIjhrflbqK8aYKr4Sn3C6Q8GGQaGg1IGexXmMt2W9KWsjgA=
---

# 微信公众号（wechat-mp）

Shadeling 产品型积木（`kind: product`，V2 小程序包）。

面向微信公众号（订阅号 / 服务号）的本地运营助手：在原生 macOS 应用里完成
**Markdown 撰写 → 微信兼容 HTML 排版 → 图片上传永久素材 → 创建草稿 → （有权限时）发布** 的完整链路。

- 积木 id：`com.shadeling.brick.wechat-mp`
- 版本：`1.0.0`
- 入口 bundle：`WeChatMP.app`
- 网络权限：`network`（仅访问 `https://api.weixin.qq.com`）

> 本积木以独立应用形态运行（独立窗口），由 Shadeling 作为聚合底座管理启动 / 卸载，不经过内核 IPC。

---

## 1. 目录结构

```
products/wechat-mp/
├── manifest.json                    # 积木清单（brick-app/v1 契约）
├── icon.png                         # 占位图标（1024×1024）
├── README.md                        # 本文件
├── .gitignore                       # 忽略 .build/ 构建缓存与打包中间产物
├── source/                          # SwiftPM 源码（macOS 15.0+）
│   ├── Package.swift
│   ├── Info.plist                   # 打包 .app 用的模板（复制进 .app/Contents/）
│   ├── package_app.sh               # 构建 → 组装 .app → 打 zip（含 manifest.json）→ 回填 sha256
│   └── Sources/WeChatMP/
│       ├── WeChatMPApp.swift        # @main 应用入口
│       ├── AppState.swift           # 全局状态（账号 / 素材 / 草稿 / 发布权限）
│       ├── Models.swift             # 数据模型
│       ├── Core/
│       │   ├── CredentialStore.swift  # 账号配置本地持久化
│       │   ├── TokenManager.swift     # access_token 缓存 + 刷新 + 失效重试
│       │   ├── WeChatAPI.swift        # URLSession 网络层
│       │   └── WeChatError.swift      # 错误码 → 可读提示
│       ├── Services/
│       │   ├── MediaService.swift     # 永久素材上传
│       │   ├── DraftService.swift     # 草稿新增 / 列表 / 删除
│       │   └── PublishService.swift   # 发布（freepublish）与权限探测
│       ├── Markdown/
│       │   ├── MarkdownRenderer.swift # Markdown → 微信兼容 HTML
│       │   └── Themes.swift           # 内置排版主题
│       └── Views/
│           ├── RootView.swift
│           ├── AccountView.swift
│           ├── ComposerView.swift
│           ├── MediaView.swift
│           ├── DraftListView.swift
│           ├── PublishView.swift
│           └── HTMLPreviewView.swift
└── releases/
    └── 1.0.0/                       # 构建产物（见 §4）
        ├── wechat-mp-1.0.0.zip
        └── wechat-mp-1.0.0.zip.sha256
```

---

## 2. 功能模块

| 模块 | 说明 |
|---|---|
| 账号配置 | 填写 AppID / AppSecret，持久化到本机私有目录；提供「测试连接」分步校验凭据、IP 白名单与发布权限 |
| 内容编辑 | Markdown 编辑器 + 实时预览；内置 2 套微信兼容排版主题，输出全部使用内联样式的 HTML 片段 |
| 素材 | 选择本地图片上传为**永久素材**，返回 `media_id` 与微信图片 URL，可直接作为草稿封面 |
| 草稿 | 创建草稿（标题 / 作者 / 摘要 / 正文 HTML / 封面 `thumb_media_id`）、草稿列表、删除草稿 |
| 发布 | 仅当账号具备 `freepublish` 权限时显示入口；无权限时隐藏并给出后台认证说明 |
| 网络层 | `URLSession` 调 `api.weixin.qq.com`；`access_token` 缓存 + 过期自动刷新 + 失效（40001/42001）自动重试一次；对 `40164 / 40165 / 40007 / 48001` 等错误码给出中文可读提示 |

---

## 3. 凭据与安全

- **源码不含任何凭据**：AppID / AppSecret 只由用户在应用界面内填写，写入
  `~/Library/Application Support/com.shadeling.brick.wechat-mp/account.json`（权限 `0600`）。
- 该目录与应用源码、git 仓库、`manifest.json` 完全无关，卸载积木时不会随包分发，也不会被上传。
- 应用只访问 `https://api.weixin.qq.com`，不访问任何第三方服务。
- 请在公众平台后台按最小必要原则维护 IP 白名单，发现异常调用及时重置 AppSecret。

---

## 4. 本地构建与打包（本次未执行）

前置：macOS 15.0+、Xcode Command Line Tools（`swift --version` 可用）。

### 4.1 编译源码

```bash
cd products/wechat-mp/source
swift build -c release
# 产物：.build/release/WeChatMP
```

### 4.2 组装 .app 并打 zip（一条命令）

```bash
cd products/wechat-mp/source
bash package_app.sh 1.0.0
```

脚本会依次完成：

1. `swift build -c release`
2. 组装 `dist/WeChatMP.app`（`Contents/MacOS/WeChatMP`、`Contents/Info.plist`、`Contents/Resources/icon.png`）
3. 暂存包内 `dist/manifest.json`（`scripts/pack_product.py stage`：只带身份字段）
4. 打包 `releases/1.0.0/wechat-mp-1.0.0.zip`（zip 根目录即 `WeChatMP.app` + `manifest.json`）
5. `scripts/pack_product.py finalize`：计算 sha256 → 写 `wechat-mp-1.0.0.zip.sha256` → 自动回填 `manifest.json` 与 `index.json` 的 `products[]` → 复核 zip 内容

> **zip 内必须含 `manifest.json`**：安装器（`AppModel.installBrick`）解压后要读包内 manifest 才能确认积木身份 / 入口 bundle / 权限声明，缺了会直接中止安装。`verify_products.py` 已把该条做成发布闸门，同类包出不了仓库。

### 4.3 手动等价步骤（不想用脚本时）

```bash
cd products/wechat-mp/source
swift build -c release
mkdir -p dist/WeChatMP.app/Contents/MacOS dist/WeChatMP.app/Contents/Resources
cp .build/release/WeChatMP dist/WeChatMP.app/Contents/MacOS/
cp Info.plist dist/WeChatMP.app/Contents/
cp ../icon.png dist/WeChatMP.app/Contents/Resources/
python3 ../../scripts/pack_product.py stage --product wechat-mp --out dist/manifest.json
mkdir -p ../releases/1.0.0
cd dist && zip -r -X ../../releases/1.0.0/wechat-mp-1.0.0.zip WeChatMP.app manifest.json
cd ../.. && python3 ../../scripts/pack_product.py finalize --product wechat-mp --version 1.0.0
```

---

## 5. sha256 回填与包内 manifest（重要）

当前 `manifest.json` 中已回填 `1.0.0` 的实算校验和：

```json
"sha256": "1a0fd7637206bd83d90ce7ec9cf61351d10f6da0da9020925efc71e360ec2c80"
```

该值（含 `index.json` `products[]` 中的同名条目）由出包脚本自动回填，**不再手工维护**。后续发布新版本时：

1. 执行 §4.2 一条命令：`scripts/pack_product.py finalize` 会算 sha256、写 `.sha256`、回填 `manifest.json` + `index.json`，并复核 zip 内含 `manifest.json`（缺则报错不出包）。
2. 运行产品闸门自检：

   ```bash
   python3 scripts/verify_products.py wechat-mp
   ```

   期望输出 `[OK] wechat-mp`（该闸门不在 CI 内，必须手动执行）。

> 包内 `manifest.json` **不含** `sha256` / `download_url`：二者是仓库侧发布元数据，且 zip 无法包含自身哈希（回填即失效）。安装器只读身份 / 权限字段，不依赖它们。
> 注意：处于 `PENDING_BUILD` 占位状态时，闸门会因 `releases/<version>/<name>-<version>.zip` 不存在而报「发布产物缺失」，属预期。

---

## 6. 微信公众平台后台配置

1. 登录 [微信公众平台](https://mp.weixin.qq.com) → **设置与开发 → 基本配置**。
2. 记录 **AppID**；点击「重置」生成 / 查看 **AppSecret**（开发者密码）。
3. **IP 白名单**：同一页面「IP 白名单」中加入本机公网出口 IP：

   ```bash
   curl ifconfig.me
   ```

   未加入白名单时接口返回 `errcode: 40164, invalid ip`。白名单修改约 5 分钟后生效；家庭宽带 / 移动网络的出口 IP 可能变化，需重新确认。
4. 草稿接口**不需要**配置服务器 URL / Token，无需开启服务器模式。

### 6.1 账号类型与接口权限

| 能力 | 个人订阅号 | 企业订阅号（已认证） | 服务号（已认证） |
|---|---|---|---|
| 获取 `access_token` | ✅ | ✅ | ✅ |
| 素材管理（上传图片 / 缩略图） | ✅ | ✅ | ✅ |
| 草稿箱（新增 / 查询 / 删除） | ✅ | ✅ | ✅ |
| 发布 `freepublish` | ⚠️ 已回收 | ✅ | ✅ |

> 2025 年 7 月起，微信官方已回收个人主体账号与未认证企业账号的 `freepublish` 权限。
> 这类账号仍可正常创建草稿，但**最终发布需在公众号后台手动完成**——应用会隐藏发布入口并给出说明。

### 6.2 常见错误码

| errcode | 含义 | 处理 |
|---|---|---|
| 40001 | `access_token` 无效或已过期 | 应用会自动刷新并重试一次；仍失败请检查 AppID / AppSecret |
| 40007 | 无效的 `media_id` | 封面 / 素材不存在或不属于当前账号，重新上传 |
| 40013 / 40125 | AppID / AppSecret 无效 | 核对后台基本配置，必要时重置开发者密码 |
| 40164 | 调用来源 IP 不在白名单 | 将本机公网 IP 加入 IP 白名单 |
| 40165 | 无效 IP | 白名单未生效或出口 IP 已变化，更新后重试 |
| 45009 | 接口调用频次超限 | 稍后重试 |
| 48001 | api 功能未授权 | 账号类型 / 认证状态不支持该接口（发布接口需认证的企业订阅号或服务号） |

---

## 7. 状态

- [x] `manifest.json`（10 个必填字段齐全）
- [x] `source/` 源码骨架（SwiftPM executableTarget，macOS 15.0）
- [x] `README.md`
- [x] `icon.png` 占位图标
- [x] `releases/1.0.0/wechat-mp-1.0.0.zip`（内含 `manifest.json`）与 sha256 回填（sha256 = `1a0fd7637206bd83d90ce7ec9cf61351d10f6da0da9020925efc71e360ec2c80`）
- [x] `index.json` 登记（`products[]` 已追加同名条目）
*（内容由AI生成，仅供参考）*
