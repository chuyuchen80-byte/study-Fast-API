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
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import UPLOAD_DIR
from app.database import Base, engine
from app.routers.posts import router as posts_router
from app.routers.users import router as users_router

# =========================================================================
# 1. 创建 FastAPI 应用实例
# =========================================================================
# 这就是整个后端的核心对象！
# 所有路由、中间件、事件处理器都挂在这个 app 上
# uvicorn app.main:app → uvicorn 会找到这个 app 对象并启动 ASGI 服务器
app = FastAPI()


# =========================================================================
# 2. CORS 中间件 —— 允许前端跨域访问
# =========================================================================
# 为什么需要 CORS？
#   前端运行在 http://127.0.0.1:5173（Vite 开发服务器）
#   后端运行在 http://127.0.0.1:8000（FastAPI / Uvicorn）
#   浏览器安全策略：不同端口 = 不同源 = 默认禁止跨域请求
#   CORS 中间件告诉浏览器："我是允许这些来源访问的"
#
# Django 对比：django-cors-headers 包的 CORS_ALLOWED_ORIGINS 配置项
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",  # Vite 开发服务器地址
        "http://localhost:5173",   # 另一种写法（127.0.0.1 和 localhost 在浏览器眼里是不同源）
    ],
    allow_credentials=True,  # 允许携带 Cookie / Authorization 头（JWT token 需要这个）
    allow_methods=["*"],     # 允许所有 HTTP 方法（GET, POST, PUT, DELETE, PATCH 等）
    allow_headers=["*"],     # 允许所有请求头（包括我们自定义的 Authorization）
)

# =========================================================================
# 3. 路由注册 —— Django 的 urls.py 里的 include()
# =========================================================================
# include_router() 把 APIRouter 挂到 app 上
# users_router 的 prefix="/user" 在 routers/users.py 里定义
# posts_router 的 prefix="/posts" 在 routers/posts.py 里定义
# → 最终路径 = prefix + @router上的路径
# 例如：posts_router.prefix="/posts" + @router.get("/{post_id}")
#      → 完整路径 = GET /posts/{post_id}
app.include_router(users_router)
app.include_router(posts_router)

# =========================================================================
# 4. 静态文件挂载 —— Django 的 STATIC_URL + STATIC_ROOT
# =========================================================================
# app.mount() 把整个 /static/uploads/ 路径映射到磁盘上的 app/uploads/ 目录
# 效果：GET /static/uploads/abc.png → 返回 app/uploads/abc.png 文件
#
# 注意：mount 必须在 include_router 之后！
#   因为 FastAPI 按注册顺序匹配路由，mount 放在最后可以确保 /user/ 和 /posts/ 优先匹配
#   如果 mount 在前面，/static/uploads 会拦截所有以 /static 开头的请求
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# =========================================================================
# 5. 生命周期事件 —— Django 的 AppConfig.ready() 对应物
# =========================================================================
# on_event("startup"): 应用启动时执行一次（建立数据库连接、创建表等）
# on_event("shutdown"): 应用关闭时执行一次（释放连接等）

@app.on_event("startup")
async def startup():
    """应用启动时：自动创建数据库表 + 测试连接"""
    # create_all：根据 models.py 里的模型自动创建对应的数据库表
    # 如果表已经存在 → 跳过（不会覆盖或修改已有表）
    # 相当于 Django 的 python manage.py migrate（但不会检测模型变更）
    # 生产环境建议用 Alembic 代替 create_all（类似 Django migrations）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 测试数据库连接：SELECT 1
    # text("SELECT 1") 是纯 SQL 语句（不用 ORM）
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("数据库连接成功?", result.scalar())  # 应该输出 1


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时：释放数据库连接池"""
    await engine.dispose()  # 关闭所有数据库连接
