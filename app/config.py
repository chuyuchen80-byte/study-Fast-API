"""
=============================================================================
 config.py —— 全局配置中心（Django 的 settings.py 对应物）
=============================================================================

Django 对比：
   Django 把所有配置放在 settings.py 一个文件里（DATABASES、SECRET_KEY 等）
   FastAPI 没有约定配置文件名，我们自己在 config.py 集中管理

设计原则：
   1. 先调用 load_dotenv() 加载 .env 文件（开发环境用 .env，生产环境用真正的环境变量）
   2. 每个配置项先用 os.getenv() 读环境变量
   3. 环境变量不存在时提供合理的默认值（方便本地开发）
   4. 生产环境必须通过环境变量覆盖敏感信息（密码、密钥等）
"""

import os

from dotenv import load_dotenv

# =========================================================================
# 0. 加载 .env 文件 —— 在读取任何配置之前！
# =========================================================================
# load_dotenv() 会从项目根目录的 .env 文件中读取 KEY=VALUE 并注入到 os.environ
# .env 文件只在开发环境用，生产环境直接用真正的环境变量
# Django 对比：python-dotenv 不在 Django 里标配，但 python-decouple 或 django-environ 类似
#
# 注意：必须在所有 os.getenv() 调用之前执行！
load_dotenv()

# =========================================================================
# 1. 数据库配置 —— Django 的 DATABASES['default']
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
# 2. JWT 认证配置 —— Django 的 SECRET_KEY + JWT 相关设置
# =========================================================================
# SECRET_KEY：JWT 签名密钥，相当于 Django 的 SECRET_KEY
#   生产环境务必改成随机长字符串并通过环境变量传入！
#   os.urandom(32).hex() 可以生成一个随机的 64 字符密钥
SECRET_KEY = os.getenv("SECRET_KEY", "fastapi_blog_secret_key")

# ALGORITHM：JWT 签名算法，HS256 是最常用的对称加密算法
#   对称 = 签发和验证用同一把密钥，简单高效
#   非对称（RS256）需要公私钥对，更安全但更复杂
ALGORITHM = "HS256"

# ACCESS_TOKEN_EXPIRE_MINUTES：访问令牌过期时间（分钟）
#   30 分钟后 token 失效，用户需要用 refresh_token 续期
#   短期有效 = 即使被盗，影响也有限
#   生产环境通常设 15-60 分钟
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# REFRESH_TOKEN_EXPIRE_DAYS：刷新令牌过期时间（天）
#   7 天内可以免重新登录换取新的 access_token
#   比 access_token 长很多，因为只在"换新"时用一次，不那么频繁暴露
# Django 对比：Django Simple JWT 的 SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# =========================================================================
# 3. 文件上传配置 —— Django 的 MEDIA_ROOT + 上传限制
# =========================================================================
# UPLOAD_DIR：上传图片的存储目录（绝对路径）
#   os.path.dirname(__file__)  = app/ 目录（当前 config.py 所在位置）
#   os.path.join(..., "uploads") = app/uploads/
#   启动时自动创建目录（exist_ok=True 表示已经存在也不报错）
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# AVATAR_DIR：用户头像存储目录
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

# MAX_UPLOAD_SIZE：上传文件最大大小（字节），默认 5MB
# Django 对比：Django settings 里的 DATA_UPLOAD_MAX_MEMORY_SIZE
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(5 * 1024 * 1024)))  # 5MB

# ALLOWED_IMAGE_TYPES：允许上传的图片 MIME 类型
# 只允许常见图片格式，拒绝 .exe、.php 等恶意文件
# 为什么不用后缀名判断？后缀名可以伪造（把 .exe 改名为 .jpg），MIME 类型由浏览器根据文件内容判断
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# =========================================================================
# 4. 应用配置
# =========================================================================
# APP_TITLE：应用名称（显示在 Swagger /docs 和页面标题）
APP_TITLE = os.getenv("APP_TITLE", "FastAPI Blog 论坛")

# APP_VERSION：应用版本号
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")

# DEBUG：是否调试模式
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")