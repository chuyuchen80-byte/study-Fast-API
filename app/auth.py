"""
=============================================================================
 auth.py —— 认证与授权（Django 的 authentication + @login_required 对应物）
=============================================================================

Django 对比：
   Django 内置了完整的 auth 系统：
     - authenticate() + login()  → 验证用户
     - @login_required           → 要求登录
     - request.user              → 获取当前用户
     - User.objects.create_user()→ 创建用户（自动哈希密码）
     - settings.SECRET_KEY       → JWT 密钥

   FastAPI 没有内置 auth，需要手动实现：
     - 密码哈希用 hashlib（简单但够用，生产环境建议用 passlib + bcrypt）
     - JWT 签发/校验用 python-jose
     - 获取当前用户用 Depends(get_current_user)
     - 要求登录就是在路由里声明 Depends(get_current_user)

核心概念：
   1. hash_password()       —— 注册/登录时对明文密码做 SHA-256 哈希
   2. create_access_token() —— 登录成功后签发 JWT（JSON Web Token）
   3. get_current_user()    —— 每次需要登录的请求过来，解密 JWT → 查用户

JWT（JSON Web Token）是什么？
   一串由三部分组成的加密字符串：Header.Payload.Signature
   - Header：  {"alg": "HS256"}  — 签名算法
   - Payload： {"sub": "用户名", "exp": 过期时间}  — 实际数据
   - Signature: 用 SECRET_KEY 对前两部分签名  — 防篡改
   服务端拿到 token 后验证签名 → 确认没被篡改 → 信任 payload 里的数据
   好处：服务端不需要存 session，token 本身包含所有信息（无状态）
"""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from app.database import get_db
from app.models import User
from app.schemas import TokenData

# ---------------------------------------------------------------------------
# OAuth2PasswordBearer：告诉 FastAPI "从请求头的 Authorization: Bearer xxx 拿 token"
# ---------------------------------------------------------------------------
# tokenUrl="/user/login" 有两个作用：
#   1. 告诉前端去哪个接口获取 token
#   2. OpenAPI 文档（/docs）里会显示一个"Authorize"按钮，点了就调这个接口
# Django 对比：相当于 LOGIN_URL = '/user/login'
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login")


# ---------------------------------------------------------------------------
# hash_password：密码哈希（Django 的 make_password / User.set_password 对应物）
# ---------------------------------------------------------------------------
# 为什么用哈希而不是存明文？
#   如果数据库泄露，攻击者拿不到用户的实际密码
#   验证时：对用户输入的密码做同样的哈希 → 比对哈希值
#
# SHA-256 的特点：
#   优点：简单、快速、Python 标准库自带
#   缺点：没有加盐（salt），同样的密码产生同样的哈希，可以用彩虹表破解
#   生产环境建议：改用 passlib + bcrypt — 自带 salt、故意算得慢（防暴力破解）
def hash_password(password: str) -> str:
    """对明文密码做 SHA-256 哈希，返回 64 位十六进制字符串"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# create_access_token：签发 JWT（Django REST Framework SimpleJWT 的 RefreshToken 对应物）
# ---------------------------------------------------------------------------
# 参数：
#   data: 要放入 token 的数据，通常是 {"sub": "用户名"}
#         "sub"（subject）是 JWT 标准字段，表示"这个 token 代表谁"
#   expires_delta: 过期时间长度，不传就用默认的 30 分钟
#
# 返回：一个加密好的 JWT 字符串，类似 "eyJhbGciOiJIUzI1NiIs..."
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """生成 JWT token"""
    # 复制一份数据，避免修改原始 dict（好习惯）
    to_encode = data.copy()

    # 计算过期时间：当前 UTC 时间 + 有效时长
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # 把过期时间写入 payload
    to_encode.update({"exp": expire})

    # 用 SECRET_KEY 签名，生成最终的 JWT 字符串
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# get_current_user：FastAPI 依赖 —— 从 JWT 中提取当前用户
# ---------------------------------------------------------------------------
# 这是整个认证系统的核心！任何需要登录的接口只要声明：
#     current_user: User = Depends(get_current_user)
# 就能拿到当前用户对象。如果没登录（没 token / token 无效 / token 过期），
# 直接返回 401，不会进入路由函数体。
#
# Django 对比：
#   相当于 @login_required + request.user 的组合
#   但这一个函数同时完成了"要求登录"和"获取用户对象"两件事
#
# 执行流程（由 FastAPI 的 Depends 机制自动串联）：
#   1. oauth2_scheme(request)        → 从 Authorization 头提取 token 字符串
#   2. jwt.decode(token)             → 解密 + 验证签名 + 检查过期时间
#   3. TokenData(username="...")     → 把 payload 里的 sub 字段取出来
#   4. 用 username 查数据库           → 拿到 User ORM 对象
#   5. return User 对象              → 路由函数直接使用
#
# 任何一步失败 → 抛出 401 → 路由函数体根本不会执行
async def get_current_user(
    token: str = Depends(oauth2_scheme),  # 步骤1：从请求头拿 token
    db: AsyncSession = Depends(get_db),    # 步骤2：获取数据库会话（在步骤4用到）
) -> User:
    """从 JWT token 中解析出当前登录用户。失败则返回 401。"""

    # 定义一个"未登录"异常，多处可能会抛，统一写在一处
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,  # 401 = 未授权
        detail="无效的登录状态，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},    # 告诉浏览器"需要 Bearer token"
        # Django 对比：这个头让浏览器弹出登录框（不常用，但规范要求）
    )

    try:
        # 步骤3：解密 JWT，验证签名是否正确、是否过期
        # jwt.decode 内部做两件事：
        #   (1) 用 SECRET_KEY 验证签名 → 确认 token 没被篡改
        #   (2) 检查 exp（过期时间）→ 确认 token 还有效
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 步骤4：从 payload 中取出用户名（我们签发时放在 "sub" 字段里）
        # payload.get("sub") 可能返回 None（如果 token 没问题但没 sub 字段）
        token_data = TokenData(username=payload.get("sub"))

    except JWTError as exc:
        # JWTError 是 jose 库里所有 JWT 相关异常的基类
        # 包括：签名不对、token 过期、格式不正确等
        raise credentials_exception from exc

    if token_data.username is None:
        raise credentials_exception

    # 步骤5：用用户名查数据库，获取完整的 User 对象
    # Django 对比：request.user 是框架自动帮你查好的
    # FastAPI 需要手动查，但好处是你可以控制查哪些字段、是否 join 关联表
    result = await db.execute(
        select(User).where(User.username == token_data.username)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # 用户可能在签发 token 后被删除了
        raise credentials_exception

    return user  # 返回的是 SQLAlchemy ORM 对象，路由函数可以直接用 user.id, user.username
