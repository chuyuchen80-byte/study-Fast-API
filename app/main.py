import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password
from app.database import Base, engine, get_db
from app.models import User
from app.routers.posts import router as posts_router
from app.schemas import Token, UserLogin, UserRegister, UserResponse

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


# ── 用户路由 ──────────────────────────────────────────────


@app.post("/user/register")
async def register(user: UserRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    db_user = User(
        username=user.username,
        password_hash=hash_password(user.password),
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return {
        "message": "注册成功",
        "user": UserResponse.model_validate(db_user),
    }


@app.post("/user/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalar_one_or_none()

    if not db_user or db_user.password_hash != hash_password(user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token({"sub": db_user.username})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(db_user),
        "message": "登录成功",
    }


@app.get("/user/me")
async def read_current_user(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@app.get("/user/list")
async def lists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [UserResponse.model_validate(user) for user in users]


# ── 论坛路由 ──────────────────────────────────────────────

app.include_router(posts_router)

# 静态文件服务（上传的图片）
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


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
