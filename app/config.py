"""配置：全部通过环境变量注入，不写死任何路径或凭证。"""

import os


def _bool(value, default=False):
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on", "y")


def _list(value, sep=":"):
    if not value:
        return []
    return [item.strip() for item in value.split(sep) if item.strip()]


# 媒体库根目录，多个用冒号分隔；容器内只读挂载即可
MEDIA_DIRS = _list(os.getenv("MEDIA_DIRS", "/media"))

# 飞牛影视数据库文件
TRIM_DB = os.getenv("TRIM_DB", "/trim/db/trimmedia.db")

# 飞牛影视图片目录（演员头像、封面等缓存在这里）
TRIM_IMG_DIR = os.getenv("TRIM_IMG_DIR", "/trim/img")

# 定时表达式（标准 5 段 cron），默认每天 02:05
CRON = os.getenv("CRON", "5 2 * * *").strip()

# 启动后立即跑一次，再按 cron 循环
RUN_ON_START = _bool(os.getenv("RUN_ON_START"), False)

# 只跑一次就退出（调试 / 定时任务外部调度时用）
RUN_ONCE = _bool(os.getenv("RUN_ONCE"), False)

# 不写数据库，只打印将要做什么
DRY_RUN = _bool(os.getenv("DRY_RUN"), False)

# 是否用 NFO 的值覆盖数据库里已有内容
OVERWRITE = _bool(os.getenv("OVERWRITE"), True)

# 下载图片用的代理，例如 http://192.168.1.2:7890
PROXY = os.getenv("PROXY", "").strip()

# 视频扩展名（用于确定 NFO 对应的正片）
MEDIA_EXTS = tuple(
    _list(
        os.getenv(
            "MEDIA_EXTS",
            ".strm:.mp4:.mkv:.avi:.wmv:.ts:.m2ts:.iso:.rmvb:.flv:.mov",
        ),
        ":",
    )
)


def _path_map(value):
    """解析路径映射：容器路径=宿主路径，多个用逗号分隔。

    飞牛影视数据库里存的是宿主路径，容器内看到的路径可能不同，
    匹配条目时需要把容器路径还原成宿主路径。
    """
    mapping = {}
    if not value:
        return mapping
    for pair in value.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        container, host = pair.split("=", 1)
        container = container.strip().rstrip("/")
        host = host.strip().rstrip("/")
        if container and host:
            mapping[container] = host
    return mapping


PATH_MAP = _path_map(os.getenv("PATH_MAP", ""))

# 是否下载演员头像到本地
DOWNLOAD_ACTOR_IMAGES = _bool(os.getenv("DOWNLOAD_ACTOR_IMAGES"), True)

# 首次写入前备份数据库
BACKUP_DB = _bool(os.getenv("BACKUP_DB"), True)

# 单张图片大小上限
MAX_IMG_BYTES = int(os.getenv("MAX_IMG_BYTES", "8388608"))

# 下载超时（秒）
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))

# 日志级别
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 时区（容器内生效）
TZ = os.getenv("TZ", "Asia/Shanghai")
