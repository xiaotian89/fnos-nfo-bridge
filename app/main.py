"""fnos-nfo-bridge：把 NFO 元数据同步进飞牛影视数据库。"""

import logging
import os
import sys
import time
from datetime import datetime

from croniter import croniter

import config
import images
import nfo as nfo_parser
from trimdb import TrimDB

log = logging.getLogger("bridge")


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def find_videos(directory, base_name):
    """在目录里找 NFO 对应的正片文件。"""
    try:
        entries = os.listdir(directory)
    except OSError:
        return []

    # 1) 与 NFO 同名
    for entry in entries:
        if entry == base_name:
            continue
        stem, ext = os.path.splitext(entry)
        if stem == base_name and ext.lower() in config.MEDIA_EXTS:
            return [os.path.join(directory, entry)]

    # 2) 目录下唯一的视频
    candidates = []
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        full = os.path.join(directory, entry)
        if ext.lower() in config.MEDIA_EXTS and os.path.isfile(full):
            candidates.append(full)
    return candidates if len(candidates) == 1 else []


def collect_nfo_files():
    found = []
    for root_dir in config.MEDIA_DIRS:
        if not os.path.isdir(root_dir):
            log.warning("媒体目录不存在，已跳过：%s", root_dir)
            continue
        for current, _dirs, files in os.walk(root_dir):
            for name in files:
                if name.lower().endswith(".nfo"):
                    found.append(os.path.join(current, name))
    return found


def handle_nfo(db, nfo_path):
    meta = nfo_parser.parse(nfo_path)
    if not meta:
        return "解析失败"

    directory = os.path.dirname(nfo_path)
    base_name = os.path.splitext(os.path.basename(nfo_path))[0]
    videos = find_videos(directory, base_name)

    item = None
    for video in videos:
        item = db.find_item_for_video(video)
        if item:
            break
    if not item:
        item = db.find_item_any_by_dir(directory)

    if not item:
        return "飞牛影视里还没有这个条目"

    meta["nfo_path"] = nfo_path
    changed = db.update_item(item["guid"], meta)

    people = 0
    for order, actor in enumerate(meta["actors"]):
        person_guid = db.ensure_person(actor["name"], actor.get("thumb", ""))
        if person_guid:
            db.link_person(item["guid"], person_guid, order)
            people += 1

    tags = db.set_tags(item["guid"], meta["genres"])

    return "已更新（字段 %d，演员 %d，标签 %d）" % (changed, people, tags)


def run_once():
    started = time.time()
    log.info("开始同步：媒体目录 %s", ", ".join(config.MEDIA_DIRS) or "(未配置)")

    nfo_files = collect_nfo_files()
    if not nfo_files:
        log.info("没有找到 NFO 文件")
        return

    log.info("发现 %d 个 NFO 文件", len(nfo_files))

    ok = skipped = failed = 0
    try:
        db = TrimDB(
            config.TRIM_DB,
            config.TRIM_IMG_DIR,
            dry_run=config.DRY_RUN,
            backup=config.BACKUP_DB,
            proxy=config.PROXY,
            overwrite=config.OVERWRITE,
            download_images=config.DOWNLOAD_ACTOR_IMAGES,
            http_timeout=config.HTTP_TIMEOUT,
            max_img_bytes=config.MAX_IMG_BYTES,
        ).open()
    except Exception as exc:  # noqa: BLE001
        log.error("打开数据库失败：%s", exc)
        return

    try:
        for nfo_path in nfo_files:
            name = os.path.basename(os.path.dirname(nfo_path)) or os.path.basename(nfo_path)
            try:
                result = handle_nfo(db, nfo_path)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.error("[失败] %s：%s", name, exc)
                continue

            if result.startswith("已更新"):
                ok += 1
                log.info("[完成] %s → %s", name, result)
            else:
                skipped += 1
                log.info("[跳过] %s → %s", name, result)
    finally:
        db.close()

    log.info(
        "同步结束：成功 %d，跳过 %d，失败 %d，用时 %.1f 秒",
        ok, skipped, failed, time.time() - started,
    )


def loop():
    log.info("定时任务已启动，CRON=%s，时区=%s", config.CRON, config.TZ)
    if config.RUN_ON_START:
        run_once()

    while True:
        try:
            now = datetime.now()
            next_run = croniter(config.CRON, now).get_next(datetime)
            wait_seconds = max(1.0, (next_run - now).total_seconds())
            log.info("下次执行：%s（%.0f 秒后）", next_run.strftime("%Y-%m-%d %H:%M:%S"), wait_seconds)

            while wait_seconds > 0:
                time.sleep(min(30.0, wait_seconds))
                wait_seconds -= 30.0

            run_once()
        except KeyboardInterrupt:
            log.info("收到退出信号，停止")
            return
        except Exception as exc:  # noqa: BLE001
            log.error("定时循环异常，60 秒后重试：%s", exc)
            time.sleep(60)


def main():
    setup_logging()
    if config.RUN_ONCE:
        run_once()
        return
    loop()


if __name__ == "__main__":
    main()
