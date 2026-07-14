"""
=============================================================================
 auth.py —— 认证与授权模块（Django 的 authenticate + login + Permission 对应物）
=============================================================================

Django 对比：
   Django 认证体系:                          FastAPI 认证体系:
   ─────────────                           ─────────────
   authenticate(username, password)        hash_password() + verify_password()
   login(request, user)                    create_access_token() → JWT 返回给前端
   request.user                           Depends(get_current_user)
   @login_required                        Depends(get_current_user) —— 自动返回 401
   User.has_perm("delete_post")           手动检查 (不是 Django 的权限框架)
   TokenAuthentication (DRF)              OAuth2PasswordBearer + JWT

   核心区别:
     Django 把认证状态存在服务器端 Session 里（Cookie-based）
     FastAPI 用 JWT 把认证状态存在客户端（Stateless）
     每次请求前端都要在 Authorization 头里带上 token，后端解码验证

密码哈希演进历史（写在注释里方便理解）：
   1. 最初：SHA-256 无盐哈希（不安全，彩虹表攻击）
   2. 现在：bcrypt —— 自动加 salt、故意慢（防暴力破解）、工业级标准
   3. bcrypt 原理：$2b$12$salt...hashed... → 12 = 工作因子（2^12 = 4096 次迭代）
      每次校验都要重新算 4096 次，让暴力破解慢到不可行

Django 对比：Django 默认使用 PBKDF2 + SHA-256（也是慢哈希）
Django 的 settings.PASSWORD_HASHERS 可以切换算法
"""

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from app.database import get_db
from app.models import User
from app.schemas import TokenData


# =========================================================================
# 1. 密码哈希 —— Django 的 make_password / check_password 对应物
# =========================================================================

# 使用 bcrypt 原生 API（不用 passlib，避免 passlib 1.7.4 与 bcrypt 5.0 版本冲突）
#
# Django 对比：
#   make_password("123456")       → hash_password("123456")
#   check_password("123456", h)   → verify_password("123456", h)
#
# bcrypt 原生 API：
#   bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)) → hash
#   bcrypt.checkpw(password, hashed)                   → True/False


def hash_password(password: str) -> str:
    """
    对密码进行 bcrypt 哈希（Django 的 make_password 对应物）

    bcrypt 的特点：
      1. 自动生成 random salt → 同一密码两次 hash 结果不同
      2. 计算速度刻意慢 → 防暴力破解（rounds=12 = 4096 次迭代）
      3. 输出格式：$2b$12$<22-char-salt><31-char-hash>，约 60 字符
      4. 密码限制 72 字节 → 超长密码自动截断（极为罕见的情况）
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否匹配哈希（Django 的 check_password 对应物）

    向后兼容：自动识别旧 SHA-256 格式（64 位 hex，无 $ 前缀）并用旧方式验证。
    验证成功后由调用方自动升级为 bcrypt。
    """
    # 判断是否为旧 SHA-256 哈希
    is_legacy_sha256 = (
        len(hashed_password) == 64
        and not hashed_password.startswith("$")
        and all(c in "0123456789abcdef" for c in hashed_password.lower())
    )

    if is_legacy_sha256:
        return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password

    # 新 bcrypt 密码
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def needs_password_upgrade(hashed_password: str) -> bool:
    """
    检查密码哈希是否需要从 SHA-256 升级到 bcrypt

    返回 True 表示这是一个旧的 SHA-256 哈希，应该在用户下次登录时自动升级
    返回 False 表示已经是 bcrypt 哈希，不需要升级

    使用场景：login 成功后检查，如果是旧哈希就自动 re-hash 并存回数据库
    """
    return (
        len(hashed_password) == 64
        and not hashed_password.startswith("$")
        and all(c in "0123456789abcdef" for c in hashed_password.lower())
    )


# =========================================================================
# 2. JWT 令牌管理 —— Django 的 login() + set_cookie() 对应物
# =========================================================================

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    创建 JWT 访问令牌（短有效期，用于日常 API 请求）

    Django 对比：
      相当于 Django DRF 的 TokenAuthentication.create_token()
      但 Django 的 token 存在数据库里，FastAPI 的 JWT 是无状态的

    JWT 结构（三个 Base64 部分用 . 连接）：
      Header:    {"alg": "HS256", "typ": "JWT"}        → Base64
      Payload:   {"sub": "用户名", "exp": 过期时间,
                   "type": "access"}                    → Base64
      Signature: HMAC-SHA256(Header.Base64 + "." +
                   Payload.Base64, SECRET_KEY)

    参数：
      data: 要编码到 JWT 里的数据，通常 {"sub": username}
      expires_delta: 过期时间间隔，默认 30 分钟

    注意：要 copy data 再修改，避免修改调用者的数据
    """
    to_encode = data.copy()  # 不修改原始 data（好习惯）
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    创建 JWT 刷新令牌（长有效期，用于获取新的 access_token）

    为什么需要 refresh token？
      access_token 有效期短（30 分钟）→ 即使被盗，影响有限
      refresh_token 有效期长（7 天）→ 只在 access_token 过期时用一次
      这种双令牌设计是 OAuth2 最佳实践

    注意："type": "refresh" 防止刷新令牌被当作访问令牌使用
    （get_current_user 会拒绝 type != "access" 的 token）

    Django 对比：Django 没有内置双令牌机制，这是 DRF Simple JWT 提供的功能
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# =========================================================================
# 3. 获取当前用户 —— Django 的 request.user 对应物
# =========================================================================

# OAuth2PasswordBearer: FastAPI 内置的 Bearer 令牌提取器
#   tokenUrl="/user/login": 告诉 OpenAPI 文档（Swagger UI）登录接口在哪
#   提取逻辑：Authorization: Bearer <token> → 返回 <token> 字符串
#   无 token 时 → 自动返回 401 响应（不进入你的函数）
#
# Django 对比：相当于 Django REST Framework 的 TokenAuthentication 类
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login")


# =========================================================================
# 3.5 令牌黑名单 —— 登出后立即失效 token（v2.0 新增）
# =========================================================================
# 简单的内存令牌黑名单。注意：服务重启后丢失，access_token 短有效期减轻影响。
# 生产环境建议用 Redis 存储黑名单，并设置 key 的 TTL = token 剩余有效期。
token_blacklist: set[str] = set()


def is_token_blacklisted(token: str) -> bool:
    """检查令牌是否已被加入黑名单（用户登出后失效）"""
    return token in token_blacklist


def blacklist_token(token: str):
    """将令牌加入黑名单（POST /user/logout 调用）"""
    token_blacklist.add(token)


async def get_current_user(
    token: str = Depends(oauth2_scheme),  # 从 Authorization 头提取 token
    db: AsyncSession = Depends(get_db),   # 自动注入数据库 session
) -> User:
    """
    从 JWT 令牌中解析出当前登录用户 —— 核心认证依赖

    用法：在路由函数参数里声明 current_user: User = Depends(get_current_user)
      如果 token 无效 → FastAPI 返回 401，路由函数体不会执行
      如果 token 有效 → current_user 就是当前登录的 User 对象

    验证步骤（与 Django 的 AuthenticationMiddleware 流程相似）：
      1. 从 Authorization 头提取 JWT 字符串
      2. 解码 JWT 并验证签名和过期时间
      3. 检查 token type 必须是 "access"（防止 refresh token 被当作访问令牌用）
      4. 从 payload 中提取 username（sub 字段）
      5. 查询数据库确认用户存在
      6. 返回 User ORM 对象

    为什么还要查数据库？（JWT 是无状态的啊）
      万一用户在 token 签发后被删除了呢？
      JWT 只证明"签发时用户存在"，查数据库确保"现在还存在"
      Django 的 SessionAuthentication 同理（查 DB 而不是只信 Cookie）

    Django 对比：相当于 Django 的 AuthenticationMiddleware + request.user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的登录状态，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},  # OAuth2 规范要求 401 返回这个头
    )

    try:
        # 解码 JWT — 验证签名（是否被篡改）+ 验证过期时间
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 检查 token 是否已被加入黑名单（v2.0：用户登出后立即失效）
        if is_token_blacklisted(token):
            raise credentials_exception

        # 检查 token type：防止 refresh token 被当作 access token 用
        if payload.get("type") != "access":
            raise credentials_exception

        username: str | None = payload.get("sub")  # "sub" 是 JWT 标准字段（Subject）
        if username is None:
            raise credentials_exception  # token 缺少用户名 → 无效
    except JWTError as exc:
        # JWTError: 签名错误、过期、格式不对等所有 JWT 相关异常
        raise credentials_exception from exc

    # 查询数据库确保用户仍然存在
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        # 用户可能被删除了 → 虽然 JWT 有效，但拒绝访问
        raise credentials_exception

    return user


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    可选认证依赖：有 token 就返回用户，没有就返回 None（不报 401）

    使用场景：
      GET /posts/ → 未登录可看帖子列表，已登录就额外显示 is_liked / is_favorited
      未登录时这两个字段返回 False，已登录时返回真实状态

    注意：这个函数不通过 Depends(oauth2_scheme) 获取 token，
    而是直接从请求中手动提取（用 fastapi.Request），使用方式不同

    Django 对比：相当于 Django 的 request.user.is_authenticated 检查
    ---
    由于参数签名需要手动访问 request，实际使用时会包装在中间件中
    或者在路由函数内部手动调用
    """
    # 这个简化版直接返回 None，实际使用时需要从 Request 中提取 token
    # 详见路由中的使用方式 —— GET /posts/ 的可选认证处理
    return None