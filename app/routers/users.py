"""
=============================================================================
 routers/users.py —— 用户路由（v2.0 大幅扩展）
=============================================================================

Django 对比：
   Django: urls.py + views.py + forms.py 拆分
   FastAPI: 所有用户端点集中在 APIRouter 中

端点一览：
   认证：
     POST   /user/register      → 注册（bcrypt 哈希）
     POST   /user/login         → 登录（验证密码 + 自动升级 SHA-256 + 返回 refresh_token）
     POST   /user/refresh       → 刷新 access_token     ⭐ v2.0 新增
     POST   /user/logout        → 登出（token 加入黑名单）⭐ v2.0 新增
   个人中心：
     GET    /user/me            → 获取当前用户信息
     PUT    /user/me            → 更新个人资料（bio/username）⭐ v2.0 新增
     PUT    /user/me/password   → 修改密码                  ⭐ v2.0 新增
     POST   /user/me/avatar     → 上传头像                  ⭐ v2.0 新增
   公开：
     GET    /user/{user_id}     → 用户公开资料              ⭐ v2.0 新增
     GET    /user/list          → 用户列表（保留旧端点）
   管理：
     PUT    /user/{user_id}/admin → 设置/取消管理员         ⭐ v2.0 新增

v2.0 密码升级策略：
   1. 注册：bcrypt 哈希（hash_password）
   2. 登录：verify_password() 兼容新旧两种哈希格式
   3. 登录成功：检测到旧 SHA-256 → 自动升级为 bcrypt
   4. 修改密码：用旧密码验证 → bcrypt 哈希新密码
   → 老用户下次登录时密码自动从 SHA-256 升级到 bcrypt，零停机迁移。
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    is_token_blacklisted,
    needs_password_upgrade,
    verify_password,
)
from app.config import (
    ALGORITHM,
    ALLOWED_IMAGE_TYPES,
    AVATAR_DIR,
    MAX_UPLOAD_SIZE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from app.database import get_db
from app.models import Comment, Post, User
from app.schemas import (
    PasswordUpdate,
    PostResponse,
    Token,
    TokenRefreshRequest,
    UserLogin,
    UserProfileDetailResponse,
    UserProfileResponse,
    UserRegister,
    UserResponse,
    UserUpdate,
)

# ── Router 定义 ───────────────────────────────────────────
# prefix="/user": 所有路由自动以 /user 开头
#   例如 @router.post("/login") → 完整路径 POST /user/login
router = APIRouter(prefix="/user", tags=["用户"])


# =========================================================================
# POST /user/register —— 用户注册（v2.0 升级 bcrypt）
# =========================================================================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    注册新用户（公开接口）。

    v2.0 变更：密码从 SHA-256 升级为 bcrypt 哈希。

    请求 body（JSON）:
      { "username": "zhangsan", "password": "123456" }

    Pydantic 自动校验:
      - username: 3-50 字符
      - password: 6-50 字符

    Django 对比：
      User.objects.create_user(username=username, password=password)
      → Django 的 create_user 自动调用 make_password 哈希密码
      → FastAPI 需要手动调用 hash_password()
    """
    # 检查用户名唯一性
    result = await db.execute(select(User).where(User.username == user.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户（bcrypt 哈希密码）
    db_user = User(
        username=user.username,
        password_hash=hash_password(user.password),  # v2.0: bcrypt（旧版是 SHA-256）
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return {
        "message": "注册成功",
        "user": UserResponse.model_validate(db_user),
    }


# =========================================================================
# POST /user/login —— 用户登录（v2.0: 兼容双哈希 + refresh_token）
# =========================================================================

@router.post("/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    用户登录，返回 JWT 双令牌（access_token + refresh_token）。

    v2.0 新增：
      1. 密码验证升级：verify_password() 兼容旧 SHA-256 + 新 bcrypt
      2. 自动升级：旧 SHA-256 密码匹配后自动升级为 bcrypt
      3. 双令牌：同时返回 access_token（30 分钟）+ refresh_token（7 天）

    Django 对比：
      authenticate(username, password) → 返回 user
      login(request, user) → 设置 session cookie
      我们的实现用 JWT 代替 session cookie

    请求 body（JSON）:
      { "username": "zhangsan", "password": "123456" }

    返回:
      {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "token_type": "bearer",
        "user": { "id": 1, "username": "zhangsan", ... },
        "message": "登录成功"
      }
    """
    # ── 步骤 1：查询用户 ───────────────────────────────────
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalar_one_or_none()

    # ── 步骤 2：验证密码（兼容双哈希） ─────────────────────
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # ── 步骤 3：自动升级旧 SHA-256 密码到 bcrypt ──────────
    # 老用户密码仍是 SHA-256 格式 → 匹配成功后用 bcrypt 重新哈希
    # 实现零停机密码算法迁移
    if needs_password_upgrade(db_user.password_hash):
        db_user.password_hash = hash_password(user.password)
        await db.commit()
        await db.refresh(db_user)

    # ── 步骤 4：签发 JWT 双令牌 ───────────────────────────
    access_token = create_access_token({"sub": db_user.username})
    refresh_token = create_refresh_token({"sub": db_user.username})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(db_user),
        "message": "登录成功",
    }


# =========================================================================
# GET /user/me —— 获取当前用户信息
# =========================================================================

@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    """
    获取当前登录用户的信息（需登录）。

    需要在请求头携带: Authorization: Bearer <access_token>
    Depends(get_current_user) 自动处理认证 → 无效 token 直接返回 401

    Django 对比：
      @login_required
      def profile(request):
          return JsonResponse({"user": UserSerializer(request.user).data})
    """
    return UserResponse.model_validate(current_user)


# =========================================================================
# PUT /user/me —— 更新个人资料（v2.0 新增）
# =========================================================================

@router.put("/me", response_model=UserResponse)
async def update_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新当前用户的个人资料（需登录，部分更新）。

    v2.0 新增端点。

    部分更新（PATCH 语义）: 只修改传了值的字段，没传的不变。

    如果修改 username，需要检查新用户名是否已被占用。

    Django 对比：
      form = UserChangeForm(request.POST, instance=request.user)
      if form.is_valid(): form.save()
    """
    # ── 更新 bio ──────────────────────────────────────────
    if payload.bio is not None:
        current_user.bio = payload.bio

    # ── 更新 username（需检查唯一性） ─────────────────────
    if payload.username is not None and payload.username != current_user.username:
        result = await db.execute(
            select(User).where(User.username == payload.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已被占用")
        current_user.username = payload.username

    await db.commit()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)


# =========================================================================
# PUT /user/me/password —— 修改密码（v2.0 新增）
# =========================================================================

@router.put("/me/password")
async def change_password(
    payload: PasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    修改当前用户的登录密码（需登录）。

    v2.0 新增端点。

    安全要求：必须提供旧密码验证身份（防止别人趁你离开时改密码）。

    Django 对比：
      form = PasswordChangeForm(user=request.user, data=request.POST)
      if form.is_valid(): form.save()
    """
    # ── 验证旧密码 ────────────────────────────────────────
    # verify_password() 兼容旧 SHA-256 + 新 bcrypt
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")

    # ── 设置新密码（bcrypt 哈希） ─────────────────────────
    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()

    return {"message": "密码修改成功"}


# =========================================================================
# POST /user/me/avatar —— 上传头像（v2.0 新增）
# =========================================================================

@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    上传用户头像（需登录）。

    v2.0 新增端点。

    处理流程：
      1. 校验文件类型（JPEG/PNG/GIF/WebP）
      2. 校验文件大小（≤5MB）
      3. 生成唯一文件名保存到 AVATAR_DIR
      4. 删除旧头像文件（防止磁盘垃圾堆积）
      5. 更新用户的 avatar_url 字段

    文件名策略：
      avatar_{user_id}_{uuid8}.png
      → 包含 user_id 便于识别，UUID8 防止冲突
    """
    # ── 步骤 1：校验文件类型 ─────────────────────────────────
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式「{file.content_type}」，仅支持：{allowed}",
        )

    # ── 步骤 2：读取并校验文件大小 ───────────────────────────
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"图片大小超过限制（最大 {max_mb:.0f}MB）",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # ── 步骤 3：生成唯一文件名 ───────────────────────────────
    ext = os.path.splitext(file.filename or ".png")[1] or ".png"
    unique_name = f"avatar_{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(AVATAR_DIR, unique_name)

    # ── 步骤 4：写入磁盘 ─────────────────────────────────────
    with open(file_path, "wb") as f:
        f.write(content)

    # ── 步骤 5：删除旧头像文件 ───────────────────────────────
    if current_user.avatar_url:
        old_filename = os.path.basename(current_user.avatar_url)
        old_path = os.path.join(AVATAR_DIR, old_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass  # 文件可能被锁定，静默跳过

    # ── 步骤 6：更新数据库 ───────────────────────────────────
    current_user.avatar_url = f"/static/uploads/avatars/{unique_name}"
    await db.commit()
    await db.refresh(current_user)

    # v2.0 bugfix: 返回完整 UserResponse 而非 {message, avatar_url}
    # 前端 SettingsView 调用 auth.updateProfileLocal(data.user || data)
    # 旧版 data.user 不存在 → fallback 到 {message, avatar_url} → 污染 store
    return {
        "message": "头像上传成功",
        "avatar_url": current_user.avatar_url,
        "user": UserResponse.model_validate(current_user),
    }


# =========================================================================
# POST /user/refresh —— 刷新 access_token（v2.0 新增）
# =========================================================================

@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    用 refresh_token 换取新的 access_token。

    v2.0 新增端点。

    为什么需要 refresh token？
      access_token 有效期只有 30 分钟 → 过期后前端用 refresh_token 换新的
      refresh_token 有效期 7 天 → 减少用户重新登录的频率
      refresh_token 也会过期 → 7 天后必须重新登录

    双令牌的安全优势：
      access_token 频繁在网络中传输 → 短期有效，即使泄露影响有限
      refresh_token 只在换新时传输一次 → 长期有效但暴露概率低
      → OAuth2 最佳实践（RFC 6749）

    流程：
      1. 解码 refresh_token，验证签名和过期时间
      2. 检查 token type 必须为 "refresh"（防止 access_token 冒充）
      3. 从 payload 提取 username → 查库确认用户仍存在
      4. 签发新的 access_token

    Django 对比：
      DRF Simple JWT 的 TokenRefreshView
    """
    # ── 解码并验证 refresh_token ───────────────────────────
    try:
        token_data = jwt.decode(
            payload.refresh_token, SECRET_KEY, algorithms=[ALGORITHM]
        )
        if token_data.get("type") != "refresh":
            raise HTTPException(
                status_code=401, detail="无效的刷新令牌（类型不匹配）"
            )
        username = token_data.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="无效的刷新令牌")
    except JWTError:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    # ── 确认用户仍存在 ──────────────────────────────────────
    result = await db.execute(select(User).where(User.username == username))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")

    # ── 签发新的双令牌（同时续期 refresh_token）────────────────
    new_access_token = create_access_token({"sub": username})
    new_refresh_token = create_refresh_token({"sub": username})

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(db_user),
    }


# =========================================================================
# GET /user/{user_id} —— 用户公开资料（v2.0 新增）
# =========================================================================

@router.get("/{user_id}", response_model=UserProfileDetailResponse)
async def get_user_profile(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取用户公开资料 + 帖子列表（公开，分页）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 统计
    post_count = (await db.execute(
        select(func.count(Post.id)).where(Post.user_id == user_id)
    )).scalar() or 0
    comment_count = (await db.execute(
        select(func.count(Comment.id)).where(Comment.user_id == user_id)
    )).scalar() or 0

    # 查用户帖子（分页）
    posts_result = await db.execute(
        select(Post)
        .options(joinedload(Post.user), joinedload(Post.images))
        .where(Post.user_id == user_id)
        .order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    posts = posts_result.unique().scalars().all()

    return {
        "user": UserProfileResponse(
            id=user.id, username=user.username,
            bio=user.bio, avatar_url=user.avatar_url,
            is_admin=user.is_admin,
            post_count=post_count, comment_count=comment_count,
        ),
        "posts": [PostResponse.model_validate(p) for p in posts],
        "total": post_count,
        "page": page,
        "page_size": page_size,
    }


# =========================================================================
# POST /user/logout —— 登出（v2.0 新增）
# =========================================================================

@router.post("/logout")
async def logout(request: Request):
    """
    用户登出，将当前 access_token 加入黑名单。

    v2.0 新增端点。

    实现原理（简单版）：
      1. 从 Authorization 头提取 Bearer token
      2. 调用 blacklist_token() 加入内存黑名单
      3. 后续请求：get_current_user 检查黑名单，已加入 → 401

    局限性（开发版可接受，生产需用 Redis）：
      - 内存存储：服务重启后黑名单丢失
      - access_token 仅 30 分钟有效期：token 过期后自动失效，不需要黑名单
      - refresh_token 暂未加入黑名单：登出后 refresh_token 仍可用到过期

    为什么重点不在 refresh_token 黑名单？
      - refresh_token 有效期长（7 天），但使用频率极低
      - 加入黑名单需要存储 7 天 → 内存方案不合适
      - 生产环境建议用 Redis 存黑名单，设置 TTL = token 剩余有效期

    Django 对比：
      logout(request) → 清除 session → request.user = AnonymousUser
    """
    # ── 提取 token ─────────────────────────────────────────
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        blacklist_token(token)  # 加入黑名单

    return {"message": "已登出"}


# =========================================================================
# PUT /user/{user_id}/admin —— 设置/取消管理员（v2.0 新增，仅管理员）
# =========================================================================

@router.put("/{user_id}/admin", response_model=UserResponse)
async def toggle_admin(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    设置或取消用户的管理员权限（Toggle，仅管理员可操作）。

    v2.0 新增端点。

    限制：
      1. 仅 is_admin=True 的用户可操作
      2. 不能操作自己（防止意外取消自己的管理员权限后无法恢复）

    Django 对比：
      @user_passes_test(lambda u: u.is_superuser)
      def toggle_staff(request, user_id):
          user = get_object_or_404(User, id=user_id)
          user.is_staff = not user.is_staff
          user.save()
    """
    # ── 权限检查：仅管理员 ─────────────────────────────────
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    # ── 不能操作自己 ───────────────────────────────────────
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的管理员状态")

    # ── 查目标用户 ─────────────────────────────────────────
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # ── Toggle 管理员状态 ──────────────────────────────────
    target_user.is_admin = not target_user.is_admin
    await db.commit()
    await db.refresh(target_user)

    return UserResponse.model_validate(target_user)


# =========================================================================
# DELETE /user/me —— 删除当前账户（v2.0 bugfix 新增）
# =========================================================================

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前登录用户的账户（需登录）。前端 SettingsView "危险区域"调用。"""
    await db.delete(current_user)
    await db.commit()
    # 204 No Content — ORM cascade 自动清除关联的帖子/评论/点赞等


# =========================================================================
# GET /user/list —— 用户列表（保留旧端点，向后兼容）
# =========================================================================

@router.get("/list", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """获取所有注册用户列表（公开接口，无分页）。保留旧端点向后兼容。"""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]