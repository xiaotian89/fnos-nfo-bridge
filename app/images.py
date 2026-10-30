"""图片下载与落地：飞牛影视只认本地文件 + 相对路径。"""

import logging
import os
import re

import requests

log = logging.getLogger("images")

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _proxies(proxy):
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def download(url, proxy="", timeout=25, max_bytes=8 * 1024 * 1024):
    """下载图片，返回二进制内容；失败返回 None。"""
    if not url:
        return None
    try:
        response = requests.get(
            url,
            timeout=timeout,
            proxies=_proxies(proxy),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                )
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("图片下载异常 %s：%s", url[:80], exc)
        return None

    if response.status_code != 200 or not response.content:
        log.warning("图片下载失败 %s：HTTP %s", url[:80], response.status_code)
        return None

    if len(response.content) > max_bytes:
        log.warning("图片过大，已跳过 %s：%s 字节", url[:80], len(response.content))
        return None

    return response.content


def store(content, img_root, key, prefix="act"):
    """把图片写入飞牛图片目录，返回相对路径（形如 /9b/3c/act-xxx.webp）。

    飞牛按扩展名取文件，内容不校验，所以 JPEG 直接以 .webp 后缀存放也能显示。
    """
    if not content:
        return ""

    key = _SAFE.sub("", str(key))
    if len(key) < 4:
        return ""

    sub_a, sub_b = key[0:2], key[2:4]
    filename = "%s-%s.webp" % (prefix, key)
    target_dir = os.path.join(img_root, sub_a, sub_b)
    target = os.path.join(target_dir, filename)

    os.makedirs(target_dir, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(content)

    try:
        os.chmod(target, 0o644)
    except OSError:
        pass

    return "/%s/%s/%s" % (sub_a, sub_b, filename)


def fetch_and_store(url, img_root, key, proxy="", timeout=25, max_bytes=8 * 1024 * 1024):
    """下载并落地，返回相对路径；失败返回空字符串。"""
    content = download(url, proxy=proxy, timeout=timeout, max_bytes=max_bytes)
    if not content:
        return ""
    return store(content, img_root, key)
