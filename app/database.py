"""
=============================================================================
 database.py —— 数据库连接与会话管理（Django 的 DATABASES + ORM 配置 对应物）
=============================================================================

Django 对比：
   Django 在 settings.py 里配 DATABASES字典，然后通过 python manage.py 管理
   FastAPI/SQLAlchemy 需要手动创建引擎、会话工厂，手动管理连接

核心概念：
   Engine    —— 数据库连接池，整个应用只创建一次（全局单例）
   Session   —— 一次数据库"会话"，每次请求创建一个，用完销毁
   Base      —— 所有 ORM 模型的基类（Django 的 models.Model）

为什么用异步（async）？
   普通同步代码：等数据库返回时，整个线程被阻塞，不能处理其他请求
   异步代码：等数据库返回时，线程可以去处理其他请求，等结果回来后继续执行
   → 同样的服务器资源能处理更多并发请求
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# ---------------------------------------------------------------------------
# Engine：数据库引擎（全局唯一，整个应用共享）
# ---------------------------------------------------------------------------
# create_async_engine() 创建一个异步引擎实例
# 参数解释：
#   echo=True      : 打印所有 SQL 语句到控制台（开发用，生产改为 False）
#   pool_size=5    : 连接池常驻连接数（类似 Django 的 CONN_MAX_AGE）
#   max_overflow=10: 超过 pool_size 后最多再创建 10 个临时连接
#   pool_pre_ping  : 每次拿连接前先 ping 一下，确保连接还有效（防止 MySQL 8小时断开）
engine = create_async_engine(
    DATABASE_URL,
    echo=True,          # Django 的 DEBUG=True 时打印 SQL，这里同理
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True, # 等同于 Django 的 CONN_HEALTH_CHECKS
)

# ---------------------------------------------------------------------------
# SessionLocal：会话工厂（每次请求调用一次，创建一个新的数据库会话）
# ---------------------------------------------------------------------------
# sessionmaker 是一个"工厂函数"的工厂——它返回一个用来创建 Session 的函数
#   class_=AsyncSession : 创建的是异步 Session（支持 await）
#   expire_on_commit=False: commit 后不把对象标记为"过期"
#     （避免在模板/序列化时还要再查一次数据库）
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# ---------------------------------------------------------------------------
# Base：所有 ORM 模型的基类
# ---------------------------------------------------------------------------
# Django 的 models.Model 是内置的，不需要手动声明
# SQLAlchemy 需要我们自己用 declarative_base() 创建一个基类
# models.py 里所有模型都继承这个 Base
Base = declarative_base()


# ---------------------------------------------------------------------------
# get_db：FastAPI 依赖注入 —— 每个请求自动获取/释放数据库会话
# ---------------------------------------------------------------------------
# 这是 FastAPI 最核心的模式之一：Depends(get_db)
#
# 工作流程（由 FastAPI 自动管理）：
#   请求进来 → 创建 session → yield session（路由函数使用）
#             → 路由函数执行完 → with 块结束 → session.close() 自动关闭
#
# Django 对比：
#   Django 的 request.db / transaction.atomic() 是框架自动管理的
#   FastAPI 需要手动写这个依赖函数，但换来了更多的控制权
#
# 为什么用 async generator 而不是普通函数？
#   yield 让 FastAPI 知道"进入时做一件事，退出时做另一件事"
#   = Django 的 middleware 的 process_request + process_response
async def get_db():
    """FastAPI 依赖：每个请求获取一个数据库会话，请求结束自动关闭"""
    async with AsyncSessionLocal() as session:
        yield session  # yield = 把 session 交给路由函数，函数结束后回到这里关闭
