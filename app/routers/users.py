"""
=============================================================================
 routers/users.py —— 用户路由（Django 的 urls.py + views.py 对应物）
=============================================================================

Django 对比：
   Django 的用户相关视图通常这样拆分：
     urls.py:
       path('register/', views.register, name='register')
       path('login/', views.login, name='login')
       path('me/', views.profile, name='profile')
     views.py:
       def register(request): ...
       def login(request): ...

   FastAPI 的路由 = URL 配置 + 视图逻辑 在同一个文件里：
     @router.post("/register")
     async def register(...): ...

   对比 Django REST Framework 的 ViewSet + Router：
     FastAPI 的 APIRouter ≈ DRF 的 DefaultRouter
     @router.get/post ≈ @action 装饰器

APIRouter 的优势：
   1. 自带 prefix —— 所有路由自动以 /user 开头
   2. 自带 tags —— OpenAPI 文档里分组显示（Swagger UI 里用户接口归到 "users" 组）
   3. 可以独立测试 —— 不启动完整 app 也能测试单个 router
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password
from app.database import get_db
from app.models import User
from app.schemas import Token, UserLogin, UserRegister, UserResponse

# ── 创建路由实例 ───────────────────────────────────────────
# prefix="/user"     : 此路由器下所有路径自动加 /user 前缀
#                     比如 @router.post("/register") → 完整路径 = /user/register
# tags=["users"]     : Swagger UI 的文档分组标签
router = APIRouter(prefix="/user", tags=["users"])


# =========================================================================
# POST /user/register —— 用户注册
# =========================================================================
# 接收 JSON body → Pydantic 自动校验 → 保存到数据库
#
# Django 对比：
#   def register(request):
#       if request.method == 'POST':
#           form = UserRegisterForm(request.POST)
#           if form.is_valid():
#               User.objects.create_user(...)
@router.post("/register")
async def register(user: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    注册新用户

    请求 body（JSON）:
      { "username": "zhangsan", "password": "123456" }

    校验逻辑：
      1. Pydantic 自动检查 username 长度 ≥ 3、password 长度 ≥ 6
      2. 手动检查用户名是否已被注册
    """
    # 检查用户名是否已存在
    # select(User).where(User.username == user.username)
    #   Django 对比：User.objects.filter(username=user.username).first()
    result = await db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalar_one_or_none()  # 查到了返回 User，查不到返回 None
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建 User ORM 对象（注意：此时还没写入数据库）
    # hash_password() 把明文密码变成 SHA-256 哈希，不存明文
    db_user = User(
        username=user.username,
        password_hash=hash_password(user.password),
    )

    # 三件套：add → commit → refresh
    # db.add(db_user)     : 把对象加入"待保存"队列
    # await db.commit()   : 真正执行 INSERT 语句（提交事务）
    # await db.refresh()  : 刷新对象，让 id 等数据库生成的字段回填到 Python 对象
    # Django 对比：user = User.objects.create(...)，这三步自动完成
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # 返回响应
    # UserResponse.model_validate(db_user) :
    #   把 ORM 对象转换成 Pydantic 对象（只取 id 和 username，不暴露 password_hash）
    # Django 对比：UserSerializer(user).data
    return {
        "message": "注册成功",
        "user": UserResponse.model_validate(db_user),
    }


# =========================================================================
# POST /user/login —— 用户登录
# =========================================================================
# response_model=Token 告诉 FastAPI：
#   "返回值按 Token schema 序列化，多余的字段自动丢弃"
#   FastAPI 会在 /docs 里自动生成响应示例
#
# Django 对比：
#   DRF 的 @action(detail=False) + TokenObtainPairView
@router.post("/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    用户登录，返回 JWT token

    请求 body（JSON）:
      { "username": "zhangsan", "password": "123456" }

    返回:
      { "access_token": "eyJ...", "token_type": "bearer", "user": {...}, "message": "登录成功" }
    """
    # 用用户名查用户
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalar_one_or_none()

    # 两步验证：
    #   1. 用户是否存在？
    #   2. 密码是否正确？（对输入的密码做同样的哈希 → 比对）
    if not db_user or db_user.password_hash != hash_password(user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 签发 JWT token
    # {"sub": db_user.username} : "sub" 是 subject（主题）的缩写，JWT 标准字段
    #   将来 get_current_user 从 sub 里取用户名
    access_token = create_access_token({"sub": db_user.username})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(db_user),
        "message": "登录成功",
    }


# =========================================================================
# GET /user/me —— 获取当前登录用户信息
# =========================================================================
# 这个接口需要登录才能访问！
# current_user: User = Depends(get_current_user) 实现了"要求登录"
#   → get_current_user 从 JWT 解析用户 → 如果没 token 或 token 无效 → 返回 401
#   → 路由函数体只有在认证成功后才执行
#
# Django 对比：
#   @login_required
#   def profile(request):
#       return JsonResponse({"user": request.user.username})
@router.get("/me")
async def read_current_user(
    current_user: User = Depends(get_current_user),  # ← 这行就是"要求登录"
):
    """
    获取当前登录用户的信息

    需要在请求头携带：Authorization: Bearer <token>
    不需要手动写任何 if 判断 —— Depends(get_current_user) 自动处理认证
    如果 token 无效，根本不会进这个函数体，直接返回 401
    """
    return UserResponse.model_validate(current_user)


# =========================================================================
# GET /user/list —— 获取所有用户列表
# =========================================================================
# 这是一个公开接口（不需要登录），用于演示
# 生产环境中通常需要分页 + 限制返回字段
@router.get("/list")
async def list_users(db: AsyncSession = Depends(get_db)):
    """
    获取所有注册用户列表（公开，无分页）

    select(User) 不带 .where() → 查全部用户
    Django 对比：User.objects.all()
    """
    result = await db.execute(select(User))
    users = result.scalars().all()  # .scalars() 提取每行的第一个字段（User 对象），.all() 转列表

    # 列表推导式：每个 ORM 对象转成 Pydantic 对象
    return [UserResponse.model_validate(user) for user in users]
