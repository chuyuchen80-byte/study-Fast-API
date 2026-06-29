import os

# ── Database ──────────────────────────────────────────────
# 生产环境请通过环境变量 DATABASE_URL 覆盖
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:root@localhost/fast_api_blog?charset=utf8mb4",
)

# ── Auth ──────────────────────────────────────────────────
# 生产环境请通过环境变量 SECRET_KEY 覆盖
SECRET_KEY = os.getenv("SECRET_KEY", "fastapi_blog_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ── Uploads ───────────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
