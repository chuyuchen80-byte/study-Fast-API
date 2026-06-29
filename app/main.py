from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import UPLOAD_DIR
from app.database import Base, engine
from app.routers.posts import router as posts_router
from app.routers.users import router as users_router

app = FastAPI()

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

# ── 路由挂载 ──────────────────────────────────────────────

app.include_router(users_router)
app.include_router(posts_router)

# 静态文件服务（上传的图片）
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ── 生命周期 ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("数据库连接成功?", result.scalar())


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
