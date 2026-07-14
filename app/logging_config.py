"""
=============================================================================
 logging_config.py —— 日志配置（v2.0 新增文件）
=============================================================================

Django 对比：
   Django 在 settings.py 中配置 LOGGING 字典（Python logging 标准库）
   FastAPI 同样使用 Python 标准 logging 库，这里集中管理配置

日志级别（从低到高）：
   DEBUG   → 开发调试信息（变量值、SQL 查询等）
   INFO    → 一般运行信息（请求记录、启动完成等）
   WARNING → 警告信息（可恢复的问题）
   ERROR   → 错误信息（请求失败、数据库异常等）
   CRITICAL → 严重错误（服务崩溃级别）

日志输出目标：
   console → 控制台（开发环境实时查看）
   file    → 日志文件（持久化存储，便于事后排查）
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logging():
    """
    配置应用日志系统。

    v2.0 新增函数，在 main.py 的 startup 事件中调用。

    输出方式：
      1. 控制台（StreamHandler）：实时输出到 stdout，适合开发调试
      2. 文件（RotatingFileHandler）：持久化保存到 logs/app.log

    RotatingFileHandler 说明：
      - 日志文件达到 maxBytes 大小时自动轮转（改名备份、创建新文件）
      - backupCount 指定保留的备份文件数量（超出的自动删除）
      - 避免日志文件无限增长撑爆磁盘

    日志格式：
      时间 | 级别 | 模块名 | 消息
      例如：2024-01-15 10:30:45 | INFO | app.routers.posts | 帖子创建成功

    Django 对比：
      Django 的 LOGGING 字典配置（settings.py）
      FastAPI 可以用同样的 logging.config.dictConfig()，但函数式配置更灵活
    """

    # ── 1. 获取根日志器 ────────────────────────────────────
    # 根日志器会接收所有模块的日志（除非模块自己创建了独立 logger）
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 最低级别设为 DEBUG，handler 各自再过滤

    # ── 2. 日志格式 ────────────────────────────────────────
    # asctime     : 时间戳（默认格式：2024-01-15 10:30:45,123）
    # levelname   : 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    # name        : 日志器名称（通常等于模块名，如 app.routers.posts）
    # message     : 日志消息文本
    # datefmt     : 自定义时间格式（去掉毫秒，更简洁）
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── 3. 控制台 Handler（输出到 stdout） ──────────────────
    # stream=sys.stdout : 输出到标准输出（控制台）
    # setLevel(DEBUG)   : 控制台显示所有级别日志（包括 DEBUG）
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ── 4. 文件 Handler（持久化到磁盘） ──────────────────────
    # 日志文件存放在项目根目录的 logs/ 目录
    # 文件达到 10MB 时自动轮转，保留最近 5 个备份文件
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=os.path.join(log_dir, "app.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB 一个文件
            backupCount=5,               # 最多保留 5 个备份
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)  # 文件只记录 INFO 及以上（减少磁盘写入）
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError:
        # 如果日志目录创建失败（如权限不足），静默跳过——不影响应用正常运行
        pass

    # ── 5. 降低第三方库的日志噪音 ──────────────────────────
    # SQLAlchemy echo=True 已经在打印 SQL，不需要再通过日志输出
    # uvicorn.access 会打印每个 HTTP 请求，已经够用了
    # 这里降低部分第三方库的日志级别，减少控制台噪音
    for lib in ["sqlalchemy.engine", "aiomysql", "passlib"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    # ── 6. 启动确认 ────────────────────────────────────────
    logging.getLogger(__name__).info("日志系统初始化完成")