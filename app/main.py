"""
=============================================================================
 main.py —— FastAPI 应用入口（Django 的 urls.py 根配置 + wsgi.py 对应物）
=============================================================================

Django 对比：
   一个 Django 项目的入口有多个文件：
     settings.py  → 全局配置（对应我们的 config.py）
     urls.py      → 根路由配置（include 子路由）
     wsgi.py/asgi.py → 应用实例创建
     manage.py    → 启动入口

   FastAPI 把这些都浓缩到了 main.py：
     app = FastAPI()           ← 应用实例
     app.include_router(...)   ← URL 分发（Django 的 include()）
     app.add_middleware(...)   ← 中间件（Django 的 MIDDLEWARE 列表）
     app.mount("/static", ...) ← 静态文件（Django 的 STATIC_URL）
     @app.on_event("startup")  ← 启动时执行（Django 的 AppConfig.ready()）

   运行方式：
     Django: python manage.py runserver
     FastAPI: uvicorn app.main:app --reload
              ↑      ↑        ↑    ↑
              服务器  模块路径  实例  热重载

v2.0 变化：
   - 新增日志系统（logging_config.setup_logging）
   - 新增 API 限流（slowapi Limiter）
   - 新增通知路由 + 分类/标签路由
   - 新增头像静态文件挂载
   - 从 config 读取 app.title 和 app.version
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import APP_TITLE, APP_VERSION, AVATAR_DIR, UPLOAD_DIR
from app.database import Base, engine
from app.logging_config import setup_logging
from app.routers.categories import router as categories_router
from app.routers.notifications import router as notifications_router
from app.routers.posts import fav_router, router as posts_router
from app.routers.users import router as users_router


# =========================================================================
# 1. 日志初始化（最先执行）
# =========================================================================
setup_logging()

import logging

logger = logging.getLogger("app")


# =========================================================================
# 2. 创建 FastAPI 应用实例
# =========================================================================
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="一个全栈论坛项目 —— 后端 FastAPI + 前端 Vue 3",
)

# =========================================================================
# 3. API 限流配置（slowapi —— Django 的 django-ratelimit 对应物）
# =========================================================================
# Limiter 使用请求的客户端 IP 作为限流 key
# 默认限制：100 次/分钟（全局兜底，具体端点上加更细粒度的限制）
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# SlowAPI 中间件 —— 必须在所有其他中间件之前添加
app.add_middleware(SlowAPIMiddleware)


# =========================================================================
# 4. CORS 中间件 —— 允许前端跨域访问
# =========================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
# 5. 请求日志中间件 —— 记录每个 HTTP 请求的方法、路径、状态码和耗时
# =========================================================================
# Django 对比：Django 的 request/response middleware 或 django-request-logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个 HTTP 请求的方法、路径、状态码和耗时"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        "%s %s → %d (%.3fs)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


# =========================================================================
# 6. 路由注册 —— Django 的 urls.py 里的 include()
# =========================================================================
app.include_router(users_router)
app.include_router(fav_router)   # 收藏端点（定义在 posts.py，共享 /user 前缀）
app.include_router(posts_router)
app.include_router(notifications_router)
app.include_router(categories_router)


# =========================================================================
# 7. 静态文件挂载 —— Django 的 STATIC_URL + STATIC_ROOT
# =========================================================================
app.mount("/static/uploads/avatars", StaticFiles(directory=AVATAR_DIR), name="avatars")
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# =========================================================================
# 8. 生命周期事件 —— Django 的 AppConfig.ready() 对应物
# =========================================================================
# v2.0: 使用 asynccontextmanager 替代 on_event（FastAPI 推荐新写法）

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """应用生命周期管理 —— 启动时创建表 + 测试连接，关闭时释放连接池"""
    # ── 启动阶段 ──────────────────────────────────────────
    logger.info("应用启动中...")

    # 自动创建数据库表（如果不存在）
    # 生产环境建议用 Alembic 替代 create_all（类似 Django migrations）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 测试数据库连接
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        logger.info("数据库连接成功: %s", result.scalar())

    logger.info("应用启动完成（%s v%s）", APP_TITLE, APP_VERSION)

    yield  # ← 应用在这里运行

    # ── 关闭阶段 ──────────────────────────────────────────
    logger.info("应用关闭中...")
    await engine.dispose()
    logger.info("数据库连接池已释放")


app.router.lifespan_context = lifespan