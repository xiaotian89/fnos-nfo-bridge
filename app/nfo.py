"""NFO（Kodi / Emby XML 格式）解析。"""

import logging
import xml.etree.ElementTree as ET

log = logging.getLogger("nfo")


def _text(node, tag, default=""):
    element = node.find(tag)
    if element is not None and element.text:
        return element.text.strip()
    return default


def _all_text(node, tag):
    values = []
    for element in node.findall(tag):
        if element.text and element.text.strip():
            values.append(element.text.strip())
    return values


def _int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def parse(path):
    """解析 NFO 文件，返回统一结构的字典；解析失败返回 None。"""
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001
        log.warning("NFO 解析失败 %s：%s", path, exc)
        return None

    # 有的 NFO 用 <movie> 包裹，有的直接是根节点
    movie = root.find("movie")
    if movie is not None:
        root = movie

    title = _text(root, "title")
    original_title = _text(root, "originaltitle") or title
    plot = _text(root, "plot") or _text(root, "outline")
    runtime = _int(_text(root, "runtime"))
    premiered = _text(root, "premiered") or _text(root, "releasedate")
    year = _text(root, "year")
    studio = _text(root, "studio")
    mpaa = _text(root, "mpaa")

    genres = _all_text(root, "genre") + _all_text(root, "tag")

    actors = []
    for actor in root.findall("actor"):
        name = _text(actor, "name")
        if not name:
            continue
        actors.append({"name": name, "thumb": _text(actor, "thumb")})

    # 番号：JavSP 会写 <uniqueid type="num">，也有用 <num> 的
    num = ""
    for unique in root.findall("uniqueid"):
        if (unique.get("type") or "").lower() in ("num", "cid"):
            if unique.text and unique.text.strip():
                num = unique.text.strip()
                break
    if not num:
        num = _text(root, "num")

    if not premiered and year:
        premiered = "%s-01-01" % year

    # 成人内容判定：带番号或有码/无码标签
    is_adult = bool(num) or any(g in ("无码", "有码", "無修正") for g in genres)

    return {
        "title": title,
        "original_title": original_title,
        "num": num,
        "plot": plot,
        "runtime": runtime,
        "premiered": premiered,
        "studio": studio,
        "mpaa": mpaa,
        "genres": [g for g in dict.fromkeys(genres) if g],
        "actors": actors,
        "is_adult": is_adult,
    }
