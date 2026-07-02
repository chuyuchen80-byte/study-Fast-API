"""
=============================================================================
 config.py —— 全局配置中心（Django 的 settings.py 对应物）
=============================================================================

Django 对比：
   Django 把所有配置放在 settings.py 一个文件里（DATABASES、SECRET_KEY 等）
   FastAPI 没有约定配置文件名，我们自己在 config.py 集中管理

设计原则：
   1. 每个配置项先用 os.getenv() 读环境变量
   2. 环境变量不存在时提供合理的默认值（方便本地开发）
   3. 生产环境必须通过环境变量覆盖敏感信息（密码、密钥等）
"""

import os

# =========================================================================
# 数据库配置 —— Django 的 DATABASES['default']
# =========================================================================
# os.getenv("环境变量名", "默认值")
# 第一个参数：环境变量名，生产环境用来覆盖
# 第二个参数：本地开发的默认值（硬编码仅用于方便开发，生产环境不要用）
#
# URL 格式：mysql+aiomysql://用户名:密码@主机/数据库名?charset=utf8mb4
#   mysql+aiomysql 表示"用 aiomysql 驱动连 MySQL"（aiomysql 是 async 驱动）
#   如果用的是 PostgreSQL，这里会变成 postgresql+asyncpg://...
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:root@localhost/fast_api_blog?charset=utf8mb4",
)

# =========================================================================
# JWT 认证配置 —— Django 的 SECRET_KEY + JWT 相关设置
# =========================================================================
# SECRET_KEY：JWT 签名密钥，相当于 Django 的 SECRET_KEY
#   生产环境务必改成随机长字符串并通过环境变量传入！
#   os.urandom(32).hex() 可以生成一个随机的 64 字符密钥
SECRET_KEY = os.getenv("SECRET_KEY", "fastapi_blog_secret_key")

# ALGORITHM：JWT 签名算法，HS256 是最常用的对称加密算法
#   对称 = 签发和验证用同一把密钥，简单高效
#   非对称（RS256）需要公私钥对，更安全但更复杂
ALGORITHM = "HS256"

# ACCESS_TOKEN_EXPIRE_MINUTES：Token 过期时间（分钟）
#   30 分钟后 token 失效，用户需要重新登录
#   生产环境通常设 15-60 分钟，配合 refresh token 使用
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# =========================================================================
# 文件上传配置 —— Django 的 MEDIA_ROOT
# =========================================================================
# UPLOAD_DIR：上传图片的存储目录（绝对路径）
#   os.path.dirname(__file__)  = app/ 目录（当前 config.py 所在位置）
#   os.path.join(..., "uploads") = app/uploads/
#   启动时自动创建目录（exist_ok=True 表示已经存在也不报错）
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
