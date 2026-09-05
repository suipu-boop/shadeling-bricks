# products/ — 产品积木发布区（市场 V2）

本目录存放**可独立下载安装的产品积木**（`kind=product`），每个积木一个子目录，
对应 Shadeling 积木市场里能真实下载、安装、卸载的独立小程序包。

> 契约：`specs/brick-market-v2.md`（积木市场 V2）
> 底座系统工具（`bricks/` 冻结区 23 条）不进市场，不在此发布。

## 目录约定

```
products/<id>/
├── manifest.json        # BrickManifest（schema 见下）
├── source/              # 积木源码（可选，便于审阅/本地构建）
└── releases/
    └── <version>/<id>-<version>.zip   # 构建产物（市场下载对象）
    └── <version>/<id>-<version>.zip.sha256
```

## manifest.json 字段（brick-app/v1）

```json
{
  "schema": "brick-app/v1",
  "id": "com.shadeling.brick.<id>",
  "name": "<id>",
  "title": "显示名",
  "version": "1.0.0",
  "author": "Shadeling",
  "summary": "一句话简介",
  "kind": "product",
  "bundle": "<入口>.app",
  "icon": "icon.png",
  "min_os": "15.0",
  "permissions": [],
  "download_url": "https://github.com/suipu-boop/shadeling-bricks/raw/main/products/<id>/releases/<version>/<id>-<version>.zip",
  "sha256": "<zip 校验和>",
  "release_notes": ""
}
```

## index.json 登记

上架时把该积木的对外卡片字段（name/kind/version/title/summary/download_url/sha256）
追加进仓库根 `index.json` 的 `products[]` 数组——Shadeling 市场只读 `products` 数组。

## 发布自检（过闸门才能 push）

- manifest 字段完整、`kind=product`、`name` 与目录一致；
- releases/<version>/ 下 zip 存在且 sha256 与 manifest 一致；
- index.json products[] 已登记该版本；
- id 唯一，不与已发布积木冲突。
