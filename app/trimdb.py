"""飞牛影视（fnOS trim.media）SQLite 数据库操作。

飞牛影视对无法匹配自家影片库的文件会直接降级成「视频」，不会读取 NFO，
所以这里把 NFO 的元数据直接写进它的数据库，并补齐演员、标签和头像。
"""

import logging
import os
import shutil
import sqlite3
import time
import uuid

import images

log = logging.getLogger("trimdb")


class TrimDB:
    def __init__(self, path, img_root, dry_run=False, backup=True, proxy="",
                 overwrite=True, download_images=True, http_timeout=25,
                 max_img_bytes=8 * 1024 * 1024, path_map=None):
        self.path = path
        self.img_root = img_root
        self.dry_run = dry_run
        self.backup = backup
        self.proxy = proxy
        self.overwrite = overwrite
        self.download_images = download_images
        self.http_timeout = http_timeout
        self.max_img_bytes = max_img_bytes
        self.path_map = path_map or {}
        self._backed_up = False
        self._columns = {}
        self.conn = None

    def to_host_path(self, path):
        """把容器内路径还原成数据库里的宿主路径。"""
        for container_prefix, host_prefix in self.path_map.items():
            if path == container_prefix:
                return host_prefix
            if path.startswith(container_prefix + os.sep):
                return host_prefix + path[len(container_prefix):]
        return path

    # ---------- 连接 ----------

    def open(self):
        if not os.path.exists(self.path):
            raise FileNotFoundError("数据库不存在：%s" % self.path)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.row_factory = sqlite3.Row
        self._load_columns()
        return self

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc_info):
        self.close()

    def _load_columns(self):
        for table in ("item", "person", "item_person", "item_tag"):
            rows = self.conn.execute("PRAGMA table_info(%s)" % table).fetchall()
            self._columns[table] = {row["name"] for row in rows}

    def has_column(self, table, column):
        return column in self._columns.get(table, set())

    def _ensure_backup(self):
        if self._backed_up or not self.backup:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = "%s.nfo-bridge-%s.bak" % (self.path, stamp)
        try:
            shutil.copy2(self.path, target)
            log.info("已备份数据库：%s", os.path.basename(target))
        except OSError as exc:
            log.warning("数据库备份失败（继续执行）：%s", exc)
        self._backed_up = True

    # ---------- 查询 ----------

    def find_item_for_video(self, video_path):
        """按视频路径找条目，优先 Video，其次同目录的 Directory。"""
        host_path = self.to_host_path(video_path)
        row = self.conn.execute(
            "SELECT guid, type, path FROM item WHERE path = ? LIMIT 1", (host_path,)
        ).fetchone()
        if row:
            return row

        directory = self.to_host_path(os.path.dirname(video_path))
        row = self.conn.execute(
            "SELECT guid, type, path FROM item WHERE path = ? AND type = 'Directory' LIMIT 1",
            (directory,),
        ).fetchone()
        return row

    def find_item_any_by_dir(self, directory):
        host_dir = self.to_host_path(directory)
        return self.conn.execute(
            "SELECT guid, type, path FROM item WHERE path = ? LIMIT 1", (host_dir,)
        ).fetchone()

    # ---------- 写入 ----------

    def update_item(self, guid, meta):
        """更新影片元数据；只写数据库里真实存在的列。"""
        values = {
            "title": meta.get("title"),
            "original_title": meta.get("original_title"),
            "sort_title": meta.get("num") or meta.get("title"),
            "overview": meta.get("plot"),
            "runtime": meta.get("runtime") or 0,
            "release_date": meta.get("premiered") or None,
            "adult": 1 if meta.get("is_adult") else 0,
            "status": "Released",
            "fetch_status": 1,
            "type": "Movie",
            "nfo_path": meta.get("nfo_path"),
        }
        if meta.get("mpaa"):
            values["content_ratings"] = meta["mpaa"]

        payload = {}
        for column, value in values.items():
            if not self.has_column("item", column):
                continue
            if value is None or value == "":
                continue
            if not self.overwrite and self._has_value(guid, column):
                continue
            payload[column] = value

        if not payload:
            return 0

        if self.dry_run:
            log.info("[dry-run] 将更新 %s：%s", guid[:8], ", ".join(sorted(payload)))
            return len(payload)

        self._ensure_backup()
        assignments = ", ".join("%s = ?" % column for column in payload)
        params = list(payload.values())
        if self.has_column("item", "update_time"):
            assignments += ", update_time = ?"
            params.append(int(time.time() * 1000))
        params.append(guid)
        cursor = self.conn.execute(
            "UPDATE item SET %s WHERE guid = ?" % assignments, params
        )
        self.conn.commit()
        return cursor.rowcount

    def _has_value(self, guid, column):
        row = self.conn.execute(
            "SELECT %s FROM item WHERE guid = ?" % column, (guid,)
        ).fetchone()
        return bool(row and row[0])

    def ensure_person(self, name, thumb_url=""):
        """返回演员 guid；不存在则创建，并按需下载头像。"""
        row = self.conn.execute(
            "SELECT guid, profile_path FROM person WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
        if row:
            guid = row["guid"]
            if not row["profile_path"] and thumb_url and self.download_images:
                self._attach_avatar(guid, thumb_url)
            return guid

        guid = uuid.uuid4().hex
        now = int(time.time() * 1000)
        payload = {
            "guid": guid,
            "lan": "zh-CN",
            "name": name,
            "original_name": name,
            "know_for_department": "Acting",
            "gender": 1,
            "create_time": now,
            "update_time": now,
        }
        payload = {k: v for k, v in payload.items() if self.has_column("person", k)}

        if self.dry_run:
            log.info("[dry-run] 将新建演员：%s", name)
            return guid

        columns = ", ".join(payload)
        placeholders = ", ".join("?" for _ in payload)
        self._ensure_backup()
        self.conn.execute(
            "INSERT INTO person (%s) VALUES (%s)" % (columns, placeholders),
            list(payload.values()),
        )
        self.conn.commit()

        if thumb_url and self.download_images:
            self._attach_avatar(guid, thumb_url)

        return guid

    def _attach_avatar(self, guid, url):
        relative = images.fetch_and_store(
            url,
            self.img_root,
            guid,
            proxy=self.proxy,
            timeout=self.http_timeout,
            max_bytes=self.max_img_bytes,
        )
        if not relative:
            return False
        if self.dry_run:
            log.info("[dry-run] 头像将保存到 %s", relative)
            return True
        self.conn.execute(
            "UPDATE person SET profile_path = ?, update_time = ? WHERE guid = ?",
            (relative, int(time.time() * 1000), guid),
        )
        self.conn.commit()
        return True

    def link_person(self, item_guid, person_guid, order=0):
        exists = self.conn.execute(
            "SELECT 1 FROM item_person WHERE item_guid = ? AND person_guid = ? LIMIT 1",
            (item_guid, person_guid),
        ).fetchone()
        if exists:
            return 0
        if self.dry_run:
            return 1
        self.conn.execute(
            'INSERT INTO item_person (item_guid, person_guid, role, job, "order", department) '
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item_guid, person_guid, "", "Actor", order, ""),
        )
        self.conn.commit()
        return 1

    def set_tags(self, item_guid, tags, tag_type="Genre"):
        added = 0
        for tag in tags:
            if not tag:
                continue
            exists = self.conn.execute(
                "SELECT 1 FROM item_tag WHERE item_guid = ? AND tag = ? AND type = ? LIMIT 1",
                (item_guid, tag, tag_type),
            ).fetchone()
            if exists:
                continue
            if self.dry_run:
                added += 1
                continue
            self.conn.execute(
                "INSERT OR REPLACE INTO item_tag (item_guid, tag, type) VALUES (?, ?, ?)",
                (item_guid, tag, tag_type),
            )
            added += 1
        if added and not self.dry_run:
            self.conn.commit()
        return added
