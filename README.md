# fnos-nfo-bridge

把刮削器生成的 NFO 元数据同步进**飞牛影视（fnOS trim.media）**数据库，并自动下载演员头像。

支持自定义 cron 定时，跑在 Docker 里，随 NAS 开机自启。

---

## 为什么需要

飞牛影视刮削时先匹配它自己的影片库。匹配不到的类型（例如 JAV 番号）会被降级成「视频」，
即使目录里放了完整的 `movie.nfo` 也不会读取，结果就是：

- 有海报，没有简介 / 时长 / 发行日期
- 演员栏是空的
- 演员头像是灰色占位

这个容器把 NFO 里的数据直接写进飞牛影视的 SQLite 数据库，补齐这些字段。

---

## 功能

- 扫描媒体库目录里的 `.nfo`，自动找到对应的正片文件
- 写入影片元数据：标题、原始标题、简介、时长、发行日期、分级、成人标记
- 写入演员并建立关联
- 下载演员头像到飞牛影视图片目录，并使用相对路径挂到人物上
- 写入标签（类型 / 题材）
- 支持自定义 cron 时间、一次性执行、试运行
- 首次写入自动备份数据库

---

## 快速开始

### 单独部署

```yaml
services:
  fnos-nfo-bridge:
    image: ghcr.io/xiaotian89/fnos-nfo-bridge:latest
    container_name: fnos-nfo-bridge
    restart: unless-stopped
    environment:
      TZ: Asia/Shanghai
      MEDIA_DIRS: /media
      TRIM_DB: /trim/db/trimmedia.db
      TRIM_IMG_DIR: /trim/img
      CRON: "5 2 * * *"
      RUN_ON_START: "true"
    volumes:
      - /vol6/1000/media/download/STRM:/media:ro
      - /usr/local/apps/@appdata/trim.media/database:/trim/db
      - /usr/local/apps/@appdata/trim.media/img:/trim/img
```

```bash
docker compose up -d
docker logs -f fnos-nfo-bridge
```

### 和刮削器放在同一个 compose（推荐）

刮削器和同步器共享同一个媒体库目录，刮完就能同步，管理也只有一个文件。

```yaml
services:
  javsp-web:
    image: apecme/javsp-web:bata
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"
    environment:
      TZ: Asia/Shanghai
      HTTP_PROXY: ""
      HTTPS_PROXY: ""
      NO_PROXY: localhost,127.0.0.1
    volumes:
      - ./data:/app/data
      - /vol6/1000/media/download/STRM:/video

  fnos-nfo-bridge:
    image: ghcr.io/xiaotian89/fnos-nfo-bridge:latest
    container_name: fnos-nfo-bridge
    restart: unless-stopped
    depends_on:
      - javsp-web
    environment:
      TZ: Asia/Shanghai
      MEDIA_DIRS: /media
      TRIM_DB: /trim/db/trimmedia.db
      TRIM_IMG_DIR: /trim/img
      CRON: "5 2 * * *"
      RUN_ON_START: "true"
    volumes:
      - /vol6/1000/media/download/STRM:/media:ro
      - /usr/local/apps/@appdata/trim.media/database:/trim/db
      - /usr/local/apps/@appdata/trim.media/img:/trim/img
```

联动要点：

| 项目 | 说明 |
| --- | --- |
| 共享目录 | 两个容器挂同一个媒体库，刮削器写 NFO，同步器读 NFO |
| 执行顺序 | 刮削器 `02:00` 跑，同步器 `02:05` 跑（`CRON: "5 2 * * *"`） |
| 更快同步 | 想接近实时，把同步器改成 `CRON: "*/10 * * * *"` |
| 依赖关系 | `depends_on` 只保证启动顺序，不保证任务完成，顺序靠 cron 时间错开 |

---

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEDIA_DIRS` | `/media` | 媒体库目录，多个用 `:` 分隔 |
| `TRIM_DB` | `/trim/db/trimmedia.db` | 飞牛影视数据库路径 |
| `TRIM_IMG_DIR` | `/trim/img` | 飞牛影视图片目录 |
| `CRON` | `5 2 * * *` | 执行时间，标准 5 段 cron |
| `RUN_ON_START` | `false` | 启动后立即执行一次 |
| `RUN_ONCE` | `false` | 执行一次后退出 |
| `DRY_RUN` | `false` | 只打印动作，不写数据库 |
| `OVERWRITE` | `true` | 是否覆盖数据库已有内容 |
| `PROXY` | 空 | 下载图片使用的 HTTP 代理 |
| `DOWNLOAD_ACTOR_IMAGES` | `true` | 是否下载演员头像 |
| `BACKUP_DB` | `true` | 首次写入前备份数据库 |
| `MEDIA_EXTS` | `.strm:.mp4:.mkv:...` | 视频扩展名 |
| `HTTP_TIMEOUT` | `25` | 下载超时（秒） |
| `MAX_IMG_BYTES` | `8388608` | 单张图片大小上限 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 目录映射说明

| 宿主路径 | 容器路径 | 权限 |
| --- | --- | --- |
| 媒体库目录 | `/media` | 只读 |
| `@appdata/trim.media/database` | `/trim/db` | 读写 |
| `@appdata/trim.media/img` | `/trim/img` | 读写 |

数据库和图片目录必须挂载同一个父级目录（SQLite 的 WAL 文件在数据库同目录）。

---

## 支持范围

- NFO 格式：Kodi / Emby 通用 `<movie>` 结构
- 已解析字段：`title`、`originaltitle`、`plot`、`runtime`、`premiered`、`mpaa`、`genre`、`tag`、`actor/name`、`actor/thumb`、`uniqueid[type=num]`
- 演员去重按姓名匹配

## 已知限制

- 只处理飞牛影视**已经扫描到**的条目；新文件需要等飞牛影视先建好条目
- 飞牛影视的 `item` 表没有「片商」「预告片」字段，这两项不会写入
- 头像必须是能直接下载的图片地址，需要代理时请设置 `PROXY`
- 直接写入数据库，飞牛影视大版本升级后字段可能变化；升级后建议先 `DRY_RUN=true` 验证

---

## License

MIT
