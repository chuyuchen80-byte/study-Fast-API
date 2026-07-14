"""
=============================================================================
 routers/posts.py —— 论坛核心路由（v2.0 大幅扩展）
=============================================================================

本文件是论坛功能的核心，包含 18 个 API 端点 + 5 个辅助函数。

Django 对比：
   Django 的帖子功能通常拆成 views.py + urls.py + forms.py + services.py
   FastAPI 把端点集中在一个文件，通过装饰器定义路由
   → Django 的 ViewSet + Router 类似，但 FastAPI 用 APIRouter 封装

辅助函数（_ 前缀 = Python 约定"模块内部使用"）：
   _get_post_or_404()              → 查帖子（含 user/images/tags），不存在 → 404
   _count_comments()               → 统计帖子的评论总数
   _save_image()                   → 保存上传图片（含文件类型 + 大小校验）
   _get_like_and_favorite_status() → 获取点赞/收藏统计 + 当前用户状态
   _create_notification()          → 创建系统通知

端点一览（v2.0 新增端点标注 ⭐）：
   帖子 CRUD：
     POST   /posts/                     → 创建帖子（含分类/标签/图片）⭐
     GET    /posts/                     → 帖子列表（分页/搜索/筛选/排序）⭐
     GET    /posts/{id}                 → 帖子详情（含浏览量+点赞收藏统计）⭐
     PUT    /posts/{id}                 → 更新帖子（含分类/标签）⭐
     DELETE /posts/{id}                 → 删除帖子（作者或管理员）⭐
   评论：
     POST   /posts/{id}/comments        → 添加评论（含嵌套回复+通知）⭐
     GET    /posts/{id}/comments        → 评论列表（嵌套回复 depth 2）⭐
     PUT    /posts/{id}/comments/{cid}  → 编辑评论（仅作者）⭐
     DELETE /posts/{id}/comments/{cid}  → 删除评论（含子回复，作者或管理员）⭐
   点赞/收藏：
     POST   /posts/{id}/like            → 点赞/取消点赞（toggle + 通知）⭐
     GET    /posts/{id}/like-status     → 查询当前用户点赞状态⭐
     POST   /posts/{id}/favorite        → 收藏/取消收藏（toggle）⭐
     GET    /user/me/favorites          → 我的收藏列表（分页）⭐
   管理操作：
     POST   /posts/{id}/pin             → 置顶/取消置顶（仅管理员）⭐
     POST   /posts/{id}/feature         → 精华/取消精华（仅管理员）⭐
   图片（保留旧端点）：
     POST   /posts/{id}/images          → 为已有帖子追加图片

v2.0 数据流示意：
   创建帖子 → Form(title+content+files+category_id+tags)
            → 解析标签（str 拆分 → 查/建 Tag → 关联）
            → 校验图片（类型 + 大小）→ 保存磁盘 + 写 DB
            → 返回完整 PostResponse（含 like_count/favorite_count/tags）

   帖子列表 → 可选参数(q/category_id/tag) → 构建 SQL WHERE
            → 排序（置顶 > 精华 > 最新）
            → 可选认证（已登录 → 标记 is_liked/is_favorited）
            → 分页返回
"""

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user
from app.config import (
    ALGORITHM,
    ALLOWED_IMAGE_TYPES,
    MAX_UPLOAD_SIZE,
    SECRET_KEY,
    UPLOAD_DIR,
)
from app.database import get_db
from app.models import (
    Category,
    Comment,
    Notification,
    Post,
    PostFavorite,
    PostImage,
    PostLike,
    Tag,
    User,
)
from app.schemas import (
    CategoryResponse,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
    PostImageResponse,
    PostListResponse,
    PostResponse,
    PostUpdate,
    TagResponse,
    ToggleResponse,
)

# =========================================================================
# Router 定义
# =========================================================================
# 主路由：所有 /posts/* 端点（前缀在 main.py include 时自动应用）
#   例如 @router.post("/") → 完整路径 POST /posts/
#       @router.get("/{post_id}") → 完整路径 GET /posts/{post_id}
#
# Django 对比：DRF 的 DefaultRouter 自动生成路由，
#   FastAPI 的 APIRouter 需要手动 include 到 app 上
router = APIRouter(prefix="/posts", tags=["帖子"])

# 辅助路由：用户收藏端点（虽在 posts.py 定义，但归属 /user 前缀）
#   因为收藏逻辑和帖子模型紧密相关，放在此文件更内聚
#   在 main.py 中需额外 include 此 router
fav_router = APIRouter(prefix="/user", tags=["收藏"])


# =========================================================================
# 辅助函数（_ 前缀 = 模块内部函数，不暴露给外部调用者）
# =========================================================================

async def _get_post_or_404(post_id: int, db: AsyncSession) -> Post:
    """
    根据帖子 ID 查询帖子，不存在则返回 404。

    查询策略：一次 SQL 用 JOIN 查出帖子 + 作者 + 图片 + 标签
    → 避免 N+1 问题（访问 post.user / post.images / post.tags 不会额外查库）

    joinedload() 说明：
        joinedload(Post.user)   → LEFT JOIN users ON posts.user_id = users.id
        joinedload(Post.images) → LEFT JOIN post_images ON posts.id = post_images.post_id
        joinedload(Post.tags)   → LEFT JOIN (post_tags JOIN tags) ON posts.id = post_tags.post_id

    .unique() 说明：
        因为同时 JOIN 了多个一对多关系（images + tags），
        SQL 会产生笛卡尔积导致重复行，.unique() 去重后返回正确的 ORM 对象。

    Django 对比：
        Post.objects.select_related('user')
            .prefetch_related('images', 'tags')
            .get(id=post_id)
        → Django 的 select_related = JOIN，prefetch_related = 额外查询

    v2.0 变更：新增 joinedload(Post.tags)，确保帖子响应中包含标签信息
    """
    result = await db.execute(
        select(Post)
        .options(
            joinedload(Post.user),
            joinedload(Post.images),
            joinedload(Post.tags),
            joinedload(Post.category),
        )
        .where(Post.id == post_id)
    )
    post = result.unique().scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    return post


async def _count_comments(post_id: int, db: AsyncSession) -> int:
    """
    统计某个帖子的评论总数。

    为什么用 COUNT(*) 而不是 len(post.comments)?
        len(post.comments) → 先把所有 Comment ORM 对象加载到 Python 内存
        COUNT(*) → 数据库只需返回一个整数 → 1000 条评论只需传输几个字节

    funct.count() 是 SQLAlchemy 的聚合函数：
        select(func.count(Comment.id)) → SELECT COUNT(comments.id) FROM comments WHERE ...

    Django 对比：
        Comment.objects.filter(post_id=post_id).count()
        → 同样是 COUNT 查询，性能一致

    v2.0 变更：无变化（功能不变，但被更多端点复用）
    """
    result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post_id)
    )
    return result.scalar() or 0


async def _save_image(post_id: int, file: UploadFile, db: AsyncSession) -> PostImage:
    """
    保存一张上传图片到磁盘 + 写入数据库。

    v2.0 变更：新增文件类型校验 + 文件大小校验！

    安全校验（防止恶意文件上传 —— Django 的 Form clean 方法对应物）：
        1. 校验 MIME 类型必须属于 ALLOWED_IMAGE_TYPES
           → 为什么用 MIME 而不是后缀名？后缀名可以伪造（.exe 改名 .jpg）
              MIME 类型来自浏览器根据文件内容判断，更难伪造
           → 但 MIME 也可伪造，生产环境建议加服务端文件头验证（如 python-magic）
        2. 校验文件大小不超过 MAX_UPLOAD_SIZE（默认 5MB）
           → 防止用户上传超大文件撑爆磁盘

    文件命名策略（为什么用 UUID）：
        如果直接用原始文件名 "photo.png" → 两个用户可能上传同名文件 → 覆盖
        UUID（如 cc997a63...461.png）→ 全局唯一，几乎不可能冲突
        Django 对比：Django 会加后缀 _xxxxx 保证文件名唯一，
          我们用 UUID 完全避免冲突

    参数：
        post_id : 图片所属帖子 ID
        file    : FastAPI UploadFile（.filename 文件名, .content_type MIME, .read() 读取）
        db      : 数据库会话

    返回：
        PostImage ORM 对象（已 commit + refresh）

    异常：
        400 Bad Request — 文件类型不支持 或 文件超过大小限制
    """
    # ── 步骤 1：校验文件类型 ─────────────────────────────────
    # file.content_type 可能为 None（某些客户端不发送），跳过校验
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式「{file.content_type}」，仅支持：{allowed}",
        )

    # ── 步骤 2：读取文件内容并校验大小 ─────────────────────────
    # await file.read() → 一次性读完（≤5MB，性能可接受）
    # 大文件应使用流式写入（如 shutil.copyfileobj + 分段校验）
    content = await file.read()

    if len(content) > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE / (1024 * 1024)
        actual_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"图片大小 {actual_mb:.1f}MB 超过限制（最大 {max_mb:.0f}MB）",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # ── 步骤 3：生成唯一文件名 ─────────────────────────────────
    # os.path.splitext("photo.png") → ("photo", ".png")
    ext = os.path.splitext(file.filename or ".png")[1] or ".png"
    # uuid.uuid4().hex → 32 位随机十六进制字符串（无连字符）
    # 加上原扩展名 → 如 "cc997a6329ec4863983797a058ba8461.png"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # ── 步骤 4：写入磁盘 ─────────────────────────────────────
    # "wb" = 二进制写模式（图片是二进制，不能用 "w" 文本模式）
    with open(file_path, "wb") as f:
        f.write(content)

    # ── 步骤 5：写入数据库（元数据） ───────────────────────────
    # 只存文件名和访问 URL，图片内容已在磁盘上
    # url 格式：/static/uploads/<uuid>.png
    #   前端用 http://host:port + 此路径即可显示图片
    url = f"/static/uploads/{unique_name}"
    image = PostImage(
        post_id=post_id,
        filename=unique_name,
        url=url,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    return image


async def _get_like_and_favorite_status(
    post_id: int,
    current_user: User | None,
    db: AsyncSession,
) -> dict:
    """
    获取某个帖子的点赞/收藏统计 + 当前用户的点赞/收藏状态。

    v2.0 新增函数，被多个端点复用（列表/详情/搜索结果）。

    返回值字典结构：
        {
            "like_count": int,        # 总点赞数
            "favorite_count": int,    # 总收藏数
            "is_liked": bool,         # 当前用户是否已点赞（未登录 → False）
            "is_favorited": bool,     # 当前用户是否已收藏（未登录 → False）
        }

    为什么用 4 个独立查询而不是一次 JOIN 查出所有？
        1. 逻辑清晰，每个查询做一件事
        2. 未登录时只执行计数查询，跳过状态查询
        3. COUNT 查询非常快（主键索引），4 个查询的性能可接受
        4. 可单独优化（比如加 Redis 缓存计数查询）

    Django 对比：
        like_count = PostLike.objects.filter(post_id=post_id).count()
        is_liked = PostLike.objects.filter(post_id=post_id, user_id=user.id).exists()
    """
    # 计数查询（无论是否登录都要查）
    like_result = await db.execute(
        select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    )
    like_count = like_result.scalar() or 0

    fav_result = await db.execute(
        select(func.count(PostFavorite.id)).where(PostFavorite.post_id == post_id)
    )
    favorite_count = fav_result.scalar() or 0

    is_liked = False
    is_favorited = False

    # 状态查询（仅登录用户）
    if current_user:
        like_check = await db.execute(
            select(PostLike).where(
                PostLike.post_id == post_id,
                PostLike.user_id == current_user.id,
            )
        )
        is_liked = like_check.scalar_one_or_none() is not None

        fav_check = await db.execute(
            select(PostFavorite).where(
                PostFavorite.post_id == post_id,
                PostFavorite.user_id == current_user.id,
            )
        )
        is_favorited = fav_check.scalar_one_or_none() is not None

    return {
        "like_count": like_count,
        "favorite_count": favorite_count,
        "is_liked": is_liked,
        "is_favorited": is_favorited,
    }


async def _create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    message: str,
    related_post_id: int | None = None,
    related_comment_id: int | None = None,
) -> Notification:
    """
    创建一条系统通知。

    v2.0 新增函数，由评论/点赞等端点调用。

    通知类型说明：
        "like"     → 有人点赞了你的帖子（触发：POST /posts/{id}/like）
        "comment"  → 有人评论了你的帖子（触发：POST /posts/{id}/comments）
        "reply"    → 有人回复了你的评论（触发：POST /posts/{id}/comments with parent_id）
        "system"   → 系统通知（如帖子被设为精华）

    设计原则：
        1. 不给自己发通知（调用方负责检查 user_id != current_user.id）
        2. 异步写入不阻塞主请求（但当前实现是同步 await，未来可改为后台任务）
        3. 通知携带 related_post_id → 前端可构造跳转链接

    Django 对比：
        Django 的 signals 机制（post_save signal → 自动发通知）
        或 django-notifications 包的 notify.send()

    参数：
        user_id            : 接收通知的用户 ID（被通知人）
        type               : 通知类型（like/comment/reply/system）
        message            : 通知文案（纯文本，如 "张三 点赞了你的帖子「xxx」"）
        related_post_id    : 关联帖子 ID（可选，点击通知跳转到帖子）
        related_comment_id : 关联评论 ID（可选，跳转到具体评论）

    返回：
        新创建的 Notification ORM 对象
    """
    notification = Notification(
        user_id=user_id,
        type=type,
        message=message,
        related_post_id=related_post_id,
        related_comment_id=related_comment_id,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


def _build_post_response(
    post: Post,
    comment_count: int,
    stats: dict,
    current_user: User | None = None,
) -> PostResponse:
    """
    v2.0 新增辅助函数：将 Post ORM 对象 + 计算字段 组装成 PostResponse。

    为什么需要这个函数？
        PostResponse 包含很多非 ORM 的计算字段（comment_count、like_count 等），
        每个端点构造时都要写一大段重复代码。
        抽取为辅助函数 = 所有端点一个地方维护字段映射，修改时不会遗漏。

    参数：
        post           : Post ORM 对象（已加载 user/images/tags/category 关联）
        comment_count  : 评论总数（外部计算传入）
        stats          : _get_like_and_favorite_status() 的返回值字典
        current_user   : 可选，用于构造 user 字段（创建时传 user，其他传 post.user）

    返回：
        填充完整的 PostResponse Pydantic 对象
    """
    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        user=current_user or post.user,
        created_at=post.created_at,
        updated_at=post.updated_at,
        images=[PostImageResponse.model_validate(img) for img in post.images],
        comment_count=comment_count,
        view_count=post.view_count,
        like_count=stats["like_count"],
        favorite_count=stats["favorite_count"],
        is_liked=stats["is_liked"],
        is_favorited=stats["is_favorited"],
        is_pinned=post.is_pinned,
        is_featured=post.is_featured,
        category=CategoryResponse.model_validate(post.category) if post.category else None,
        tags=[TagResponse.model_validate(t) for t in post.tags],
    )


async def _get_optional_user(request: Request, db: AsyncSession) -> User | None:
    """
    从 HTTP 请求中尝试提取当前用户（可选认证，不强制登录）。

    v2.0 新增辅助函数，用于 GET /posts/ 和 GET /posts/{id} 的可选认证：
        - 有 token 且有效 → 返回 User 对象
        - 没有 token 或 token 无效 → 返回 None（不报 401）

    使用场景：
        帖子列表/详情对所有人公开，但登录用户能看到额外信息：
            - is_liked: 是否已点赞
            - is_favorited: 是否已收藏

    实现方式：
        手动从 Authorization 头提取 Bearer token → JWT 解码 → 查库
        → 全程 try/except 包裹，任何失败都静默返回 None

    Django 对比：
        Django 的 request.user.is_authenticated 检查
        匿名用户 request.user = AnonymousUser（is_authenticated = False）
        登录用户 request.user = User 实例
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[len("Bearer "):]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 确保是 access token（不是 refresh token）
        if payload.get("type") != "access":
            return None

        username = payload.get("sub")
        if not username:
            return None

        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    except (JWTError, Exception):
        # 任何 JWT 解码错误、数据库错误 → 静默当作未登录
        return None


# =========================================================================
# 帖子 CRUD 端点
# =========================================================================

# ── POST /posts/ —— 创建帖子（v2.0 大幅增强：分类 + 标签）──────────

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    title: str = Form(..., min_length=1, max_length=100, description="帖子标题"),
    content: str = Form(..., min_length=1, description="帖子正文（支持 Markdown）"),
    category_id: int | None = Form(None, description="分类 ID（可选）"),
    tags: str | None = Form(None, description="标签，逗号分隔，如 'python,fastapi,教程'"),
    files: list[UploadFile] | None = File(None, description="图片附件（可选，最多多张）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新帖子（需登录），支持同时上传图片 + 设置分类 + 添加标签。

    v2.0 新增功能：
        1. category_id → 帖子归类（如"技术"、"生活"）
        2. tags → 逗号分隔的标签，自动查/建 Tag 并关联
        3. 图片校验 → 文件类型（JPEG/PNG/GIF/WebP）+ 大小（≤5MB）

    请求格式：multipart/form-data（浏览器原生 FormData）
        → 不是 application/json！因为图片是二进制，不能放 JSON 里
        → Form() 接收文本字段，File() 接收文件字段

    标签处理逻辑（类似 Twitter/微博的话题标签）：
        1. 前端传 "python, fastapi, 教程"（逗号分隔）
        2. 后端 split(",") → ["python", "fastapi", "教程"]
        3. 逐个查 Tag 表 → 存在则复用，不存在则新建
        4. 通过 post.tags.append(tag) 建立多对多关联

    Django 对比：
        def create_post(request):
            form = PostForm(request.POST, request.FILES)
            if form.is_valid():
                post = form.save(commit=False)
                post.author = request.user
                post.save()
                form.save_m2m()  # ← 保存多对多（标签）需要额外一步
    """
    # ── 步骤 1：创建帖子基础记录 ──────────────────────────────
    post = Post(
        title=title,
        content=content,
        user_id=current_user.id,
    )
    # 设置分类（可选）
    if category_id is not None:
        post.category_id = category_id

    from app.models import post_tags as post_tags_table

    db.add(post)
    await db.flush()  # flush 生成 post.id，但不提交事务

    # ── 步骤 2：处理标签 ─────────────────────────────────────
    # 用 post_tags 中间表直接 INSERT，避免 post.tags.append() 触发 lazy load
    # lazy load 在 commit 后需要 greenlet 上下文，这里已经超出上下文范围
    # 直接用 SQL 插入关联表 = 绕过 ORM 的 lazy load 机制
    if tags and tags.strip():
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        for tag_name in tag_names:
            # 查找已有标签（标签名唯一）
            tag_result = await db.execute(select(Tag).where(Tag.name == tag_name))
            tag_obj = tag_result.scalar_one_or_none()
            if not tag_obj:
                tag_obj = Tag(name=tag_name)
                db.add(tag_obj)
                await db.flush()  # flush 生成 tag_id
            # 直接插入 post_tags 中间表（不用 post.tags.append，避免 lazy load）
            stmt = post_tags_table.insert().values(post_id=post.id, tag_id=tag_obj.id)
            await db.execute(stmt)
    await db.commit()

    # ── 步骤 3：处理图片上传 ─────────────────────────────────
    if files:
        for file in files:
            if not file.filename:
                continue  # 跳过空文件（浏览器可能发空 input 占位）
            # _save_image 内含文件类型 + 大小校验
            await _save_image(post.id, file, db)

    # ── 步骤 4：重新加载帖子（拿到完整的 user/images/tags） ──
    post = await _get_post_or_404(post.id, db)

    # ── 步骤 5：构造响应 ─────────────────────────────────────
    # 手动构造 PostResponse 而非 model_validate()
    # 原因：comment_count/like_count 等计算字段不是 ORM 属性，需显式传值
    return _build_post_response(post, 0, {
        "like_count": 0, "favorite_count": 0,
        "is_liked": False, "is_favorited": False,
    })


# ── GET /posts/ —— 帖子列表（v2.0：搜索 + 分类 + 标签筛选 + 多级排序 + 可选认证）─

@router.get("/", response_model=PostListResponse)
async def list_posts(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    category_id: int | None = None,
    tag: str | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """
    获取帖子列表（公开，支持分页/搜索/分类/标签筛选/多级排序/可选认证）。

    v2.0 新增功能：
        1. q 搜索 → 在标题和正文中模糊匹配
        2. category_id 筛选 → 只看某分类下的帖子
        3. tag 筛选 → 只看含某标签的帖子
        4. 多级排序 → 置顶帖 > 精华帖 > 最新帖
        5. 可选认证 → 登录后显示 is_liked/is_favorited

    URL 示例：
        GET /posts/?page=1&page_size=20                         → 全部帖子第 1 页
        GET /posts/?q=FastAPI                                   → 搜索 "FastAPI"
        GET /posts/?category_id=1&page=1                        → "技术"分类第 1 页
        GET /posts/?tag=python                                  → 含 "python" 标签的帖子
        GET /posts/?q=教程&category_id=1&tag=python&page=1     → 组合筛选

    排序策略（ORDER BY 三段式）：
        1. is_pinned DESC    → 置顶帖排最前（True=1 在 False=0 前面）
        2. is_featured DESC  → 精华帖紧随其后
        3. created_at DESC   → 同级别按最新排序
        效果：管理员置顶公告 → 精华好帖 → 最新帖子

    MySQL SQL（简化）：
        SELECT * FROM posts
        WHERE (title LIKE '%q%' OR content LIKE '%q%')
          AND category_id = 1
        ORDER BY is_pinned DESC, is_featured DESC, created_at DESC
        LIMIT 20 OFFSET 0;

    Django 对比：
        Post.objects.filter(
            Q(title__icontains=q) | Q(content__icontains=q),
            category_id=category_id,
            tags__name=tag,
        ).order_by('-is_pinned', '-is_featured', '-created_at')[0:20]

    性能注意事项：
        当前实现：对每个帖子逐一查 like_count/favorite_count/comment_count
        → N+1 问题（20 个帖子 = 60 次额外查询）
        → 生产优化：用子查询或窗口函数批量计算，或加 Redis 缓存计数器
    """
    # ── 步骤 1：可选认证（决定是否显示 is_liked/is_favorited）──
    current_user = await _get_optional_user(request, db) if request else None

    # ── 步骤 2：构建查询 ─────────────────────────────────────
    # 基础查询：加载 user/images/tags/category（避免 N+1 查关联数据）
    query = select(Post).options(
        joinedload(Post.user),
        joinedload(Post.images),
        joinedload(Post.tags),
        joinedload(Post.category),
    )

    # 基础计数查询（用于 total）
    count_query = select(func.count(Post.id))

    # 条件列表
    conditions = []

    # —— 搜索筛选 ——
    # or_(Post.title.contains(q), Post.content.contains(q))
    # → WHERE (posts.title LIKE '%q%' OR posts.content LIKE '%q%')
    # contains() 自动加 % 通配符
    if q and q.strip():
        search_term = q.strip()
        conditions.append(
            or_(
                Post.title.contains(search_term),
                Post.content.contains(search_term),
            )
        )

    # —— 分类筛选 ——
    if category_id is not None:
        conditions.append(Post.category_id == category_id)

    # —— 标签筛选 ——
    # join(Post.tags) → JOIN post_tags + tags，然后 WHERE tags.name = tag
    # 注意：join 会导致一个帖子出现多行（每个标签一行），unique() 处理
    if tag and tag.strip():
        tag_name = tag.strip()
        query = query.join(Post.tags).where(Tag.name == tag_name)
        # 计数查询也需要同样的 JOIN，用 distinct 避免因 JOIN 产生的重复计数
        count_query = (
            select(func.count(func.distinct(Post.id)))
            .select_from(Post)
            .join(Post.tags)
            .where(Tag.name == tag_name)
        )

    # 应用条件
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    # ── 步骤 3：排序 —— 置顶 > 精华 > 最新 ─────────────────
    # desc() = 降序（DESC），True(1) 排在 False(0) 前面
    query = query.order_by(
        Post.is_pinned.desc(),
        Post.is_featured.desc(),
        Post.created_at.desc(),
    )

    # ── 步骤 4：分页 ─────────────────────────────────────────
    # offset = 跳过前 N 条，limit = 只取 N 条
    # MySQL: LIMIT page_size OFFSET (page-1)*page_size
    query = query.offset((page - 1) * page_size).limit(page_size)

    # ── 步骤 5：执行查询 ─────────────────────────────────────
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query)
    posts = result.unique().scalars().all()

    # ── 步骤 6：为每个帖子构造响应对象 ────────────────────────
    post_list = []
    for post in posts:
        stats = await _get_like_and_favorite_status(post.id, current_user, db)
        comment_count = await _count_comments(post.id, db)

        post_list.append(
            _build_post_response(post, comment_count, stats)
        )

    return PostListResponse(
        posts=post_list,
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /posts/{post_id} —— 帖子详情（v2.0：浏览量 + 点赞收藏统计）──

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """
    获取单个帖子的完整详情（公开）。

    v2.0 新增功能：
        1. 浏览量递增（view_count +1）→ 作者本人访问不计数
        2. 可选认证 → 登录用户显示 is_liked/is_favorited
        3. 点赞/收藏总数统计

    浏览量计数策略：
        为什么作者访问不计数？
            - 作者编辑完通常会预览 → 不应算作"阅读"
            - 类似 YouTube 不把自己观看计入播放量
            - 如果作者看自己的帖子也算 → 容易被刷数据

    Django 对比：
        post = get_object_or_404(Post, id=post_id)
        post.view_count = F('view_count') + 1  # F() 表达式避免竞态条件
        post.save()

        我们的实现：在 Python 层 +1 → 并发时可能漏计数
        生产优化：用 UPDATE posts SET view_count = view_count + 1 WHERE id = ?
        异步下直接用 F 表达式有兼容问题，当前实现可接受
    """
    post = await _get_post_or_404(post_id, db)

    # ── 可选认证 ─────────────────────────────────────────────
    current_user = await _get_optional_user(request, db) if request else None

    # ── 浏览量 +1（作者本人不计数）──────────────────────────
    if current_user is None or current_user.id != post.user_id:
        # 直接 Python 层 +1（简单但有微小并发风险）
        post.view_count += 1
        await db.commit()
        await db.refresh(post)

    # ── 获取统计数据 ─────────────────────────────────────────
    comment_count = await _count_comments(post_id, db)
    stats = await _get_like_and_favorite_status(post_id, current_user, db)

    return _build_post_response(post, comment_count, stats)


# ── PUT /posts/{post_id} —— 更新帖子（v2.0：部分更新 + 分类/标签）──

@router.put("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    payload: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新帖子（需登录，仅限作者本人）。

    v2.0 新增功能：
        1. 部分更新（PATCH 语义）→ 传什么改什么，不传的不变
        2. 支持修改分类（category_id）
        3. 支持修改标签（tags）→ 清除旧标签 + 设置新标签

    为什么用 PUT 而不是 PATCH？
        - FastAPI 支持 PATCH，但 PUT + partial update 是常见简化做法
        - Pydantic PostUpdate 所有字段 Optional → 自然实现部分更新
        - 更规范的做法：@router.patch + 相同逻辑

    标签更新策略：
        全量替换（不是增量）：
            前端传 "python,fastapi" → 清除旧标签 → 设置新标签 → python + fastapi
        为什么不增量？（前端传 "+django" = 在原基础上加 django）：
            增量语义复杂，前端容易出错，全量替换简单可靠

    Django 对比：
        post = get_object_or_404(Post, id=post_id, author=request.user)
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
    """
    post = await _get_post_or_404(post_id, db)

    # ── 权限检查：仅作者本人可编辑 ───────────────────────────
    # Django 对比：if request.user != post.author: raise PermissionDenied
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改自己的帖子")

    # ── 部分更新：只修改传了值的字段 ─────────────────────────
    # None = "不改这个字段"（Pydantic Optional 的默认值）
    if payload.title is not None:
        post.title = payload.title
    if payload.content is not None:
        post.content = payload.content

    # 更新分类
    if payload.category_id is not None:
        post.category_id = payload.category_id

    # 更新标签（全量替换）
    if payload.tags is not None:
        # 清除旧标签关联
        post.tags.clear()
        # 设置新标签
        tag_names = [t.strip() for t in payload.tags.split(",") if t.strip()]
        for tag_name in tag_names:
            tag_result = await db.execute(select(Tag).where(Tag.name == tag_name))
            tag_obj = tag_result.scalar_one_or_none()
            if not tag_obj:
                tag_obj = Tag(name=tag_name)
                db.add(tag_obj)
                await db.flush()
            post.tags.append(tag_obj)

    # 更新修改时间
    # SQLAlchemy 的 onupdate 会自动设，但手动设一次保证数据库一致性
    post.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(post)

    # ── 重新加载完整的关联数据 ────────────────────────────────
    post = await _get_post_or_404(post_id, db)
    comment_count = await _count_comments(post_id, db)
    stats = await _get_like_and_favorite_status(post_id, current_user, db)

    return _build_post_response(post, comment_count, stats)


# ── DELETE /posts/{post_id} —— 删除帖子（v2.0：作者或管理员）──

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除帖子（需登录，作者本人或管理员可操作）。

    v2.0 变更：
        - 新增管理员权限：is_admin=True 的用户可以删除任何人的帖子
        - 删除帖子时同步清理磁盘上的图片（防止磁盘垃圾堆积）

    删除流程：
        1. 查帖子 → 不存在返回 404
        2. 验权限 → 非作者且非管理员返回 403
        3. 删磁盘图片 → os.remove() 逐个删除（.exists() 保护防止崩溃）
        4. 删数据库记录 → ORM cascade 自动删除 PostImage/Comment/PostLike 等关联记录
        5. 返回 204 No Content

    为什么图片删除放在 DB 删除之前？
        1. 如果先删 DB → ORM cascade 清除 PostImage 记录 → 就不知道图片文件名了
        2. 先删文件 → 即便后续 DB 删除失败，也只是丢了图片（可重新上传）
        3. try/except 包裹 os.remove → 文件已不存在也不会崩溃

    204 No Content 说明：
        HTTP 204 = "操作成功但没有响应体"
        浏览器收到 204 不会刷新页面，适合 DELETE 操作
        Django 对比：return HttpResponse(status=204)
    """
    post = await _get_post_or_404(post_id, db)

    # ── 权限检查：作者本人 或 管理员 ──────────────────────────
    if post.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只能删除自己的帖子（管理员除外）")

    # ── 清理磁盘上的图片 ─────────────────────────────────────
    for image in post.images:
        file_path = os.path.join(UPLOAD_DIR, image.filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                # 文件可能被锁定或权限不足 → 记录日志但不中断删除
                pass

    # ── 删除数据库记录（ORM cascade 自动清除关联数据）─────
    await db.delete(post)
    await db.commit()
    # 204 No Content → 无响应体


# =========================================================================
# 评论相关端点
# =========================================================================

# ── POST /posts/{post_id}/comments —— 添加评论（v2.0：嵌套回复 + 通知）─

@router.post(
    "/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    post_id: int,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    为帖子添加评论或回复（需登录）。

    v2.0 新增功能：
        1. 嵌套回复：parent_id 不为空 → 回复某条评论（楼中楼）
        2. 通知系统：评论帖子 → 通知作者；回复评论 → 通知被回复者

    通知策略（双重防骚扰）：
        1. 不给自己发通知（自己评论/回复自己的内容不通知）
        2. 如果回复自己的评论 → 不通知（因为就是你自己）
        3. 如果回复别人的评论，但帖子也是那个人的 → 只通知一次
           （避免同一个人收到两条几乎一样的通知）

    权限控制：
        1. parent_id 指定的父评论必须属于当前帖子（防止跨帖回复）
        2. 父评论不存在 → 400（不是 404，因为属于请求数据错误）

    Django 对比：
        Comment.objects.create(
            post=post,
            author=request.user,
            content=content,
            parent=parent_comment,
        )
    """
    # ── 确保帖子存在 ─────────────────────────────────────────
    post = await _get_post_or_404(post_id, db)

    # ── 处理父评论（嵌套回复） ───────────────────────────────
    parent_comment = None
    if payload.parent_id is not None:
        # 父评论必须属于同一个帖子（防止跨帖"嫁接"回复）
        parent_result = await db.execute(
            select(Comment).where(
                Comment.id == payload.parent_id,
                Comment.post_id == post_id,
            )
        )
        parent_comment = parent_result.scalar_one_or_none()
        if not parent_comment:
            raise HTTPException(
                status_code=400,
                detail="要回复的评论不存在或不属于本帖子",
            )

    # ── 创建评论记录 ─────────────────────────────────────────
    comment = Comment(
        content=payload.content,
        user_id=current_user.id,
        post_id=post_id,
        parent_id=payload.parent_id,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # ── 发送通知（不给自己发） ──────────────────────────────
    # 通知类型判断：
    #   有 parent_id → 回复评论（type="reply"）
    #   无 parent_id → 评论帖子（type="comment"）
    is_reply = payload.parent_id is not None

    # 通知 1：通知帖子作者（除非评论的是自己的帖子）
    if post.user_id != current_user.id:
        if is_reply:
            msg = f"{current_user.username} 回复了你在帖子「{post.title}」中的评论"
        else:
            msg = f"{current_user.username} 评论了你的帖子「{post.title}」"
        await _create_notification(
            db,
            user_id=post.user_id,
            type="reply" if is_reply else "comment",
            message=msg,
            related_post_id=post_id,
            related_comment_id=comment.id,
        )

    # 通知 2：如果回复的是别人的评论，通知父评论作者
    #   但不要重复通知（如果父评论作者就是帖子作者，上面已经通知过了）
    if parent_comment and parent_comment.user_id != current_user.id:
        if parent_comment.user_id != post.user_id:
            msg = f"{current_user.username} 回复了你在帖子「{post.title}」中的评论"
            await _create_notification(
                db,
                user_id=parent_comment.user_id,
                type="reply",
                message=msg,
                related_post_id=post_id,
                related_comment_id=comment.id,
            )

    # ── 重新加载评论（拿到 user 关联用于响应） ──────────────
    result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.id == comment.id)
    )
    comment = result.unique().scalar_one()

    return CommentResponse(
        id=comment.id,
        content=comment.content,
        user=comment.user,
        created_at=comment.created_at,
        parent_id=comment.parent_id,
        replies=[],
    )


# ── GET /posts/{post_id}/comments —— 评论列表（v2.0：嵌套回复 depth 2）─

@router.get("/{post_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    post_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取帖子的评论列表（公开），支持嵌套回复（depth 2）。

    v2.0 新增功能：
        1. 嵌套回复结构：顶级评论包含 replies 子评论列表
        2. 深度限制为 2 层（顶级 + 一级回复），避免无限嵌套

    嵌套结构示意：
        帖子
        ├── 评论 A（顶级，parent_id=None）
        │   ├── 回复 A1（parent_id=A.id）
        │   └── 回复 A2（parent_id=A.id）
        ├── 评论 B（顶级，parent_id=None）
        │   └── 回复 B1（parent_id=B.id）
        └── 评论 C（顶级，parent_id=None）

    返回的 JSON 结构：
        [
          {
            "id": 1, "content": "评论 A", "parent_id": null,
            "replies": [
              {"id": 2, "content": "回复 A1", "parent_id": 1, "replies": []},
              {"id": 3, "content": "回复 A2", "parent_id": 1, "replies": []}
            ]
          },
          ...
        ]

    查询策略：
        joinedload(Comment.user)                           → 加载评论作者
        joinedload(Comment.replies).joinedload(Comment.user) → 加载一级回复 + 回复作者
        → 一次 SQL 查出所有评论和一级回复，在 Python 层组装树结构

    Django 对比：
        用 django-mptt 或 django-treebeard 包实现树形评论
        Comment.objects.filter(post=post).select_related('user').prefetch_related('replies__user')
    """
    # ── 确认帖子存在 ─────────────────────────────────────────
    await _get_post_or_404(post_id, db)

    # ── 查询所有评论 + 一级回复 + 作者信息 ──────────────────
    # 按创建时间正序（最早的在前，模拟论坛盖楼顺序）
    result = await db.execute(
        select(Comment)
        .options(
            joinedload(Comment.user),
            joinedload(Comment.replies).joinedload(Comment.user),
        )
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    all_comments = result.unique().scalars().all()

    # ── 组装嵌套树结构 ───────────────────────────────────────
    response_list = []
    for comment in all_comments:
        # 只处理顶级评论，子评论通过 parent.replies 嵌套展示
        if comment.parent_id is not None:
            continue

        # 构造一级回复列表（depth 2：不展示更深层回复）
        replies_resp = []
        for reply in comment.replies:
            replies_resp.append(
                CommentResponse(
                    id=reply.id,
                    content=reply.content,
                    user=reply.user,
                    created_at=reply.created_at,
                    parent_id=reply.parent_id,
                    replies=[],  # depth 2 限制：不展示更深层的回复
                )
            )

        response_list.append(
            CommentResponse(
                id=comment.id,
                content=comment.content,
                user=comment.user,
                created_at=comment.created_at,
                parent_id=None,
                replies=replies_resp,
            )
        )

    return response_list


# ── PUT /posts/{post_id}/comments/{comment_id} —— 编辑评论（v2.0 新增）─

@router.put("/{post_id}/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    post_id: int,
    comment_id: int,
    payload: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    编辑自己的评论（需登录，仅限评论作者本人）。

    v2.0 新增端点。

    权限：仅评论作者本人可编辑（管理员也不能编辑别人的评论内容，
    但管理员可以删除不当评论）。

    Django 对比：
        comment = get_object_or_404(Comment, id=comment_id, post_id=post_id)
        if request.user != comment.author: raise PermissionDenied
        comment.content = request.POST['content']
        comment.save()
    """
    # ── 确认帖子存在 ─────────────────────────────────────────
    await _get_post_or_404(post_id, db)

    # ── 查评论 ───────────────────────────────────────────────
    result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.id == comment_id, Comment.post_id == post_id)
    )
    comment = result.unique().scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    # ── 权限检查：仅评论作者本人 ──────────────────────────────
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能编辑自己的评论")

    # ── 更新内容 ─────────────────────────────────────────────
    comment.content = payload.content
    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=comment.id,
        content=comment.content,
        user=comment.user,
        created_at=comment.created_at,
        parent_id=comment.parent_id,
        replies=[],
    )


# ── DELETE /posts/{post_id}/comments/{comment_id} —— 删除评论（v2.0 新增）─

@router.delete("/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    post_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除评论（需登录，作者本人或管理员可操作）。

    v2.0 新增端点。

    删除规则：
        1. 评论作者可删除自己的评论
        2. 管理员可删除任何人的评论（如违规内容）
        3. 删除评论时，其所有子回复（replies）也会被 cascade 删除
           → ORM 关系定义了 cascade="all, delete-orphan"
           → 删除父评论时，SQLAlchemy 自动删除所有 replies

    关于"删除评论后显示"的通用做法：
        有些论坛删除评论后不真删，而是标记为"已删除"（内容改为 "[该评论已被删除]"）
        这样做的好处是保留回复的上下文完整性，避免出现"回复了一条已删除评论"的困惑
        当前实现是真删除（简单直接），如需软删除可改为 is_deleted 字段

    Django 对比：
        comment = get_object_or_404(Comment, id=comment_id, post_id=post_id)
        if request.user != comment.author and not request.user.is_staff:
            raise PermissionDenied
        comment.delete()  # Django ORM 也支持 cascade 删除
    """
    # ── 确认帖子存在 ─────────────────────────────────────────
    await _get_post_or_404(post_id, db)

    # ── 查评论 ───────────────────────────────────────────────
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    # ── 权限检查：作者本人 或 管理员 ──────────────────────────
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只能删除自己的评论（管理员除外）")

    # ── 删除（cascade 自动清理子回复） ─────────────────────
    await db.delete(comment)
    await db.commit()
    # 204 No Content


# =========================================================================
# 点赞相关端点（v2.0 新增）
# =========================================================================

# ── POST /posts/{post_id}/like —— 点赞/取消点赞（toggle）────

@router.post("/{post_id}/like", response_model=ToggleResponse)
async def toggle_like(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    点赞或取消点赞（需登录，Toggle 开关模式）。

    v2.0 新增端点。

    Toggle 语义（像电灯开关：按一下开，再按一下关）：
        - 如果用户还没点赞 → 创建点赞记录（点赞）
        - 如果用户已经点过赞 → 删除点赞记录（取消点赞）
        - 不存在"重复点赞" —— 最多只能点一个赞

    为什么用 Toggle 而不是分离的 like/unlike 两个端点？
        1. 前端只需一个按钮，按钮状态（亮/灭）由 is_liked 字段决定
        2. 减少 API 数量，逻辑更简洁
        3. 用户体验好 —— 点一下就赞，再点一下就取消

    通知策略：
        - 点赞时：通知帖子作者（不给自己发通知）
        - 取消点赞时：不发送通知（取消是静默操作）

    数据库设计：
        post_likes 表有 (user_id, post_id) 组合唯一约束吗？
        当前 models.py 中没有显式唯一约束，但业务逻辑保证了唯一性
        → 生产环境建议加 UniqueConstraint('user_id', 'post_id')

    Django 对比：
        like, created = PostLike.objects.get_or_create(user=user, post=post)
        if not created:
            like.delete()  # 已存在 → 取消
    """
    # ── 确认帖子存在 ─────────────────────────────────────────
    post = await _get_post_or_404(post_id, db)

    # ── 查现有点赞记录 ───────────────────────────────────────
    result = await db.execute(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.user_id == current_user.id,
        )
    )
    existing_like = result.scalar_one_or_none()

    if existing_like:
        # ── 已点赞 → 取消点赞 ──────────────────────────────
        await db.delete(existing_like)
        await db.commit()
        active = False
    else:
        # ── 未点赞 → 点赞 ──────────────────────────────────
        new_like = PostLike(
            post_id=post_id,
            user_id=current_user.id,
        )
        db.add(new_like)
        await db.commit()

        # 发通知给帖子作者（不给自己发）
        if post.user_id != current_user.id:
            await _create_notification(
                db,
                user_id=post.user_id,
                type="like",
                message=f"{current_user.username} 点赞了你的帖子「{post.title}」",
                related_post_id=post_id,
            )

        active = True

    # ── 统计操作后的总点赞数 ────────────────────────────────
    count_result = await db.execute(
        select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    )
    like_count = count_result.scalar() or 0

    return ToggleResponse(active=active, count=like_count)


# ── GET /posts/{post_id}/like-status —— 查询当前用户点赞状态（v2.0 新增）─

@router.get("/{post_id}/like-status", response_model=ToggleResponse)
async def get_like_status(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查询当前用户对某个帖子的点赞状态（需登录）。

    v2.0 新增端点。

    使用场景：
        前端进入帖子详情页时调用，确定"点赞按钮"的初始状态（亮/灭）
        比每次都调用 toggle 端点更语义化

    返回：
        { "active": true, "count": 42 }  → 你已点赞，总共 42 个赞
        { "active": false, "count": 42 } → 你没点赞，总共 42 个赞
    """
    post = await _get_post_or_404(post_id, db)

    # 查点赞记录
    result = await db.execute(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.user_id == current_user.id,
        )
    )
    is_liked = result.scalar_one_or_none() is not None

    # 统计总数
    count_result = await db.execute(
        select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    )
    like_count = count_result.scalar() or 0

    return ToggleResponse(active=is_liked, count=like_count)


# =========================================================================
# 收藏相关端点（v2.0 新增）
# =========================================================================

# ── POST /posts/{post_id}/favorite —— 收藏/取消收藏（toggle）─

@router.post("/{post_id}/favorite", response_model=ToggleResponse)
async def toggle_favorite(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    收藏或取消收藏（需登录，Toggle 开关模式）。

    v2.0 新增端点。

    Toggle 语义与点赞一致：
        - 未收藏 → 创建收藏记录
        - 已收藏 → 删除收藏记录

    为什么收藏和点赞是独立的两个操作？
        点赞 = "我觉得这个帖子不错"（社交信号，公开可见）
        收藏 = "我想以后再看这个帖子"（私人书签，只有自己知道）
        两者的动机和可见性完全不同 → 分开存储更合适

    Django 对比：
        fav, created = PostFavorite.objects.get_or_create(user=user, post=post)
        if not created:
            fav.delete()
    """
    post = await _get_post_or_404(post_id, db)

    # 查现有收藏记录
    result = await db.execute(
        select(PostFavorite).where(
            PostFavorite.post_id == post_id,
            PostFavorite.user_id == current_user.id,
        )
    )
    existing_fav = result.scalar_one_or_none()

    if existing_fav:
        # ── 已收藏 → 取消收藏 ──────────────────────────────
        await db.delete(existing_fav)
        await db.commit()
        active = False
    else:
        # ── 未收藏 → 收藏 ──────────────────────────────────
        new_fav = PostFavorite(
            post_id=post_id,
            user_id=current_user.id,
        )
        db.add(new_fav)
        await db.commit()
        active = True

    # 统计操作后的总收藏数
    count_result = await db.execute(
        select(func.count(PostFavorite.id)).where(PostFavorite.post_id == post_id)
    )
    fav_count = count_result.scalar() or 0

    return ToggleResponse(active=active, count=fav_count)


# ── GET /user/me/favorites —— 我的收藏列表（v2.0 新增）─────

@fav_router.get("/me/favorites", response_model=PostListResponse)
async def list_my_favorites(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查看当前用户收藏的帖子列表（需登录，分页）。

    v2.0 新增端点。

    实现思路：
        1. 从 post_favorites 表查出当前用户收藏的 post_id 列表
        2. 用 post_id 列表去 posts 表查出帖子详情（JOIN user/images/tags）
        3. 按收藏时间倒序排列（最近收藏的排最前）

    Django 对比：
        favorites = PostFavorite.objects.filter(user=request.user)
            .select_related('post__author')
            .order_by('-created_at')
        posts = [fav.post for fav in favorites[0:20]]

    为什么不直接在 PostFavorite 上 joinedload(PostFavorite.post)？
        可以，但 joinedload 路径较长（PostFavorite → Post → User/Images/Tags）
        用两步查询更清晰：先查收藏记录 → 提取 post_id → 再查帖子详情
    """
    # ── 步骤 1：查收藏总数 ───────────────────────────────────
    count_result = await db.execute(
        select(func.count(PostFavorite.id)).where(
            PostFavorite.user_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # ── 步骤 2：查收藏记录（分页，按收藏时间倒序）─────────────
    fav_result = await db.execute(
        select(PostFavorite)
        .where(PostFavorite.user_id == current_user.id)
        .order_by(PostFavorite.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    favorites = fav_result.scalars().all()

    # ── 步骤 3：用收藏的 post_id 列表查询帖子详情 ────────────
    if not favorites:
        return PostListResponse(posts=[], total=total, page=page, page_size=page_size)

    post_ids = [fav.post_id for fav in favorites]

    # 查询帖子（含作者/图片/标签）
    posts_result = await db.execute(
        select(Post)
        .options(
            joinedload(Post.user),
            joinedload(Post.images),
            joinedload(Post.tags),
            joinedload(Post.category),
        )
        .where(Post.id.in_(post_ids))
    )
    posts_map = {p.id: p for p in posts_result.unique().scalars().all()}

    # ── 步骤 4：构造响应（按收藏时间顺序，不是帖子创建时间）──
    post_list = []
    for fav in favorites:
        post = posts_map.get(fav.post_id)
        if not post:
            continue  # 帖子可能已被删除

        comment_count = await _count_comments(post.id, db)
        stats = await _get_like_and_favorite_status(post.id, current_user, db)

        resp = _build_post_response(post, comment_count, stats)
        # 覆写 is_favorited=True（既然是收藏列表，一定已收藏）
        resp.is_favorited = True
        post_list.append(resp)

    return PostListResponse(
        posts=post_list,
        total=total,
        page=page,
        page_size=page_size,
    )


# =========================================================================
# 管理操作端点（v2.0 新增，仅管理员）
# =========================================================================

# ── POST /posts/{post_id}/pin —— 置顶/取消置顶 ──────────────

@router.post("/{post_id}/pin", response_model=PostResponse)
async def toggle_pin(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    置顶或取消置顶帖子（仅管理员可操作，Toggle 模式）。

    v2.0 新增端点。

    置顶效果：
        帖子列表中，置顶帖始终排在最前面（排在所有非置顶帖之前）
        多个置顶帖之间按创建时间倒序排列

    使用场景：
        - 管理员发布公告 → 置顶让所有人看到
        - 重要的教程/规范帖 → 置顶方便新人查找
        - 公告过期后 → 取消置顶

    权限：仅 is_admin=True 的用户可操作

    Django 对比：
        @user_passes_test(lambda u: u.is_staff)
        def pin_post(request, post_id):
            post = get_object_or_404(Post, id=post_id)
            post.is_pinned = not post.is_pinned
            post.save()
    """
    # ── 权限检查：仅管理员 ───────────────────────────────────
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    post = await _get_post_or_404(post_id, db)

    # ── Toggle 置顶状态 ─────────────────────────────────────
    post.is_pinned = not post.is_pinned
    await db.commit()
    await db.refresh(post)

    # ── 发送系统通知 ────────────────────────────────────────
    action = "置顶" if post.is_pinned else "取消置顶"
    if post.user_id != current_user.id:
        await _create_notification(
            db,
            user_id=post.user_id,
            type="system",
            message=f"管理员 {current_user.username} {action}了你的帖子「{post.title}」",
            related_post_id=post_id,
        )

    # ── 构造响应 ─────────────────────────────────────────────
    comment_count = await _count_comments(post_id, db)
    stats = await _get_like_and_favorite_status(post_id, current_user, db)

    return _build_post_response(post, comment_count, stats)


# ── POST /posts/{post_id}/feature —— 精华/取消精华 ──────────

@router.post("/{post_id}/feature", response_model=PostResponse)
async def toggle_feature(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    标记或取消标记精华帖（仅管理员可操作，Toggle 模式）。

    v2.0 新增端点。

    精华帖效果：
        - 帖子列表中，精华帖排在置顶帖之后、普通帖之前
        - 可以有特殊的视觉标记（前端实现，如加"精"徽章）
        - 精华帖是社区对优质内容的认可

    与置顶的区别：
        置顶 = 管理员主动推送（公告/规范）
        精华 = 管理员对优质用户内容的认可（好帖标记）
        排序：置顶 > 精华 > 普通

    权限：仅 is_admin=True 的用户可操作

    Django 对比：
        @user_passes_test(lambda u: u.is_staff)
        def feature_post(request, post_id):
            post = get_object_or_404(Post, id=post_id)
            post.is_featured = not post.is_featured
            post.save()
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    post = await _get_post_or_404(post_id, db)

    # ── Toggle 精华状态 ─────────────────────────────────────
    post.is_featured = not post.is_featured
    await db.commit()
    await db.refresh(post)

    # ── 发送系统通知 ────────────────────────────────────────
    action = "设为精华" if post.is_featured else "取消精华"
    if post.user_id != current_user.id:
        await _create_notification(
            db,
            user_id=post.user_id,
            type="system",
            message=f"管理员 {current_user.username} {action}了你的帖子「{post.title}」",
            related_post_id=post_id,
        )

    # ── 构造响应 ─────────────────────────────────────────────
    comment_count = await _count_comments(post_id, db)
    stats = await _get_like_and_favorite_status(post_id, current_user, db)

    return _build_post_response(post, comment_count, stats)


# =========================================================================
# 图片上传端点（保留旧端点，v2.0 增强校验）
# =========================================================================

# ── POST /posts/{post_id}/images —— 为已有帖子追加图片 ──────

@router.post("/{post_id}/images", response_model=list[PostImageResponse])
async def upload_images(
    post_id: int,
    files: list[UploadFile] = File(..., description="图片文件（至少一张）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    为已有帖子追加图片（需登录，仅限作者本人）。

    v2.0 变更：图片校验升级（文件类型 + 大小校验在 _save_image 中统一处理）

    使用场景：
        发帖后想补充截图/示意图 → 不需要重新编辑整个帖子
        图片追加后自动出现在帖子详情的 images 列表中

    权限：仅帖子作者本人可操作

    Django 对比：
        PostImage.objects.create(post=post, image=request.FILES['image'])
    """
    post = await _get_post_or_404(post_id, db)

    # 权限检查：仅作者
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能给自己的帖子上传图片")

    images = []
    for file in files:
        if not file.filename:
            continue
        # _save_image 内部包含类型 + 大小校验
        image = await _save_image(post_id, file, db)
        images.append(PostImageResponse.model_validate(image))

    return images