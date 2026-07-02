"""
=============================================================================
 routers/posts.py —— 论坛路由（帖子 CRUD + 评论 + 图片上传）
=============================================================================

这个文件是整个论坛功能的核心，包含 8 个 API 端点 + 3 个辅助函数。

Django 对比：
   Django: 帖子功能通常拆成 views.py + urls.py + forms.py，可能还有一个 services.py
   FastAPI: 所有端点集中在一个文件里，通过装饰器定义路由

辅助函数（下划线开头 = Python 约定"内部使用，不导出"）：
   _get_post_or_404()  → 查帖子，不存在就 404
   _count_comments()    → 统计帖子评论数
   _save_image()        → 保存上传图片（磁盘 + 数据库）

端点一览：
   POST   /posts/              → 创建帖子（需登录）
   GET    /posts/              → 帖子列表（分页）
   GET    /posts/{id}          → 帖子详情
   PUT    /posts/{id}          → 更新帖子（需登录，仅限作者）
   DELETE /posts/{id}          → 删除帖子（需登录，仅限作者）
   POST   /posts/{id}/comments → 添加评论（需登录）
   GET    /posts/{id}/comments → 评论列表
   POST   /posts/{id}/images   → 追加图片（需登录，仅限作者）
"""

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import Comment, Post, PostImage, User
from app.config import UPLOAD_DIR
from app.schemas import (
    CommentCreate,
    CommentResponse,
    PostImageResponse,
    PostListResponse,
    PostResponse,
    PostUpdate,
)

# ── 创建路由实例 ───────────────────────────────────────────
# 所有路由自动以 /posts 开头
router = APIRouter(prefix="/posts", tags=["posts"])


# =========================================================================
# 辅助函数（内部使用，不是 API 端点）
# =========================================================================

async def _get_post_or_404(post_id: int, db: AsyncSession) -> Post:
    """
    根据 ID 查询帖子，不存在则返回 404。

    为什么用 joinedload？
      普通 query 只查 Post 表 → 访问 post.user 会触发第二次查询（N+1 问题）
      joinedload(Post.user) → 一条 SQL 用 JOIN 同时查出 Post 和 User
      joinedload(Post.images) → 同时查出所有关联图片
      → 一次数据库往返拿到所有需要的数据

    Django 对比：Post.objects.select_related('user').prefetch_related('images').get(id=post_id)

    result.unique()：因为同时 join 了 user 和 images（两个一对多关系），
      SQL 会产生重复行，.unique() 去重后返回正确的 ORM 对象
    """
    result = await db.execute(
        select(Post)
        .options(joinedload(Post.user), joinedload(Post.images))
        .where(Post.id == post_id)
    )
    post = result.unique().scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    return post


async def _count_comments(post_id: int, db: AsyncSession) -> int:
    """
    统计某帖子的评论数量。

    为什么单独做一个 COUNT 查询而不是用 len(post.comments)？
      len(post.comments) 会先把所有 Comment 对象查出数据库、放到 Python 列表
      → 如果帖子有 1000 条评论，你就查了 1000 个完整的 ORM 对象
      COUNT(*) 只返回一个数字 → 速度快很多

    Django 对比：Comment.objects.filter(post_id=post_id).count()
    """
    result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post_id)
    )
    return result.scalar() or 0  # .scalar() 提取第一个结果的值


# =========================================================================
# POST /posts/ —— 创建帖子
# =========================================================================
# 这个端点用 Form() 而不是 JSON body 接收数据，因为需要同时接收文件和文本
# FormData = 可以混合普通字段 + 文件（浏览器原生支持，不用 Base64 编码图片）
#
# 参数说明：
#   title: str = Form(...)        : ... 表示必填，并且应用 min_length/max_length 校验
#   files: list[UploadFile] | None : 可选的多文件上传，不传就是 None
#   current_user = Depends(get_current_user) : 必须登录（否则返回 401）

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    title: str = Form(..., min_length=1, max_length=100),
    content: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建帖子（需登录），支持同时上传多张图片"""
    # 步骤1：创建帖子记录
    post = Post(
        title=title,
        content=content,
        user_id=current_user.id,  # 自动关联当前登录用户
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)  # 获取 post.id（数据库自增生成）

    # 步骤2：处理图片上传（如果有）
    images: list[PostImageResponse] = []
    if files:
        for file in files:
            if not file.filename:  # 跳过空文件（浏览器可能发送空 input）
                continue
            image = await _save_image(post.id, file, db)
            images.append(PostImageResponse.model_validate(image))

    # 步骤3：重新加载帖子（带 user 和 images 关联数据，用于返回完整响应）
    post = await _get_post_or_404(post.id, db)

    # 步骤4：手动构造响应
    # 为什么不用 PostResponse.model_validate(post)？
    #   因为 comment_count 不是 ORM 字段，是手动计算的值，需要显式传入
    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        user=post.user,
        created_at=post.created_at,
        updated_at=post.updated_at,
        images=images,
        comment_count=0,  # 新帖子评论数为 0
    )


# =========================================================================
# GET /posts/ —— 帖子列表（分页）
# =========================================================================
# 公开接口，不需要登录
#
# 分页参数（通过 URL 查询字符串传入）：
#   GET /posts/?page=1&page_size=20

@router.get("/", response_model=PostListResponse)
async def list_posts(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取帖子列表（公开，支持分页）"""
    # 查总数（用于前端计算总页数）
    total_result = await db.execute(select(func.count(Post.id)))
    total = total_result.scalar() or 0

    # 查当前页的帖子
    # order_by(Post.created_at.desc()) → 最新帖子排最前
    # offset((page - 1) * page_size)  → 跳过前面几页的数据
    # limit(page_size)                → 只取当前页的数据
    #
    # MySQL 的分页 SQL：SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 0;
    # Django 对比：Post.objects.order_by('-created_at')[0:20]
    result = await db.execute(
        select(Post)
        .options(joinedload(Post.user), joinedload(Post.images))
        .order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    posts = result.unique().scalars().all()

    # 为每个帖子统计评论数 + 构造响应对象
    post_list = []
    for post in posts:
        comment_count = await _count_comments(post.id, db)
        post_list.append(
            PostResponse(
                id=post.id,
                title=post.title,
                content=post.content,
                user=post.user,
                created_at=post.created_at,
                updated_at=post.updated_at,
                images=[PostImageResponse.model_validate(img) for img in post.images],
                comment_count=comment_count,
            )
        )

    return PostListResponse(
        posts=post_list,
        total=total,
        page=page,
        page_size=page_size,
    )


# =========================================================================
# GET /posts/{post_id} —— 帖子详情
# =========================================================================
# 公开接口
# {post_id} 是路径参数，FastAPI 自动从 URL 里提取并转成 int

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,  # URL 中的 {post_id} 自动注入这里
    db: AsyncSession = Depends(get_db),
):
    """获取帖子详情（公开）"""
    post = await _get_post_or_404(post_id, db)
    comment_count = await _count_comments(post_id, db)

    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        user=post.user,
        created_at=post.created_at,
        updated_at=post.updated_at,
        images=[PostImageResponse.model_validate(img) for img in post.images],
        comment_count=comment_count,
    )


# =========================================================================
# PUT /posts/{post_id} —— 更新帖子
# =========================================================================
# 需要登录 + 只能是作者本人操作
# payload: PostUpdate → JSON body 里可以只传要改的字段，没传的保持原样

@router.put("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    payload: PostUpdate,  # Pydantic 对象，不是 Form——纯文本更新用 JSON
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新帖子（需登录，仅限作者）"""
    post = await _get_post_or_404(post_id, db)

    # 权限检查：当前登录用户必须是帖子的作者
    # Django 对比：if request.user != post.author: raise PermissionDenied
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改自己的帖子")

    # 只更新传了值的字段（None = 不修改）
    # 这是"部分更新"（PATCH 语义），但用 PUT 实现
    # 更规范的做法是用 PATCH 方法 + 同样的逻辑
    if payload.title is not None:
        post.title = payload.title
    if payload.content is not None:
        post.content = payload.content

    # 更新"最后修改时间"
    # SQLAlchemy 有 onupdate 自动更新，但手动设一次确保数据库一致性
    post.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(post)

    comment_count = await _count_comments(post_id, db)

    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        user=post.user,
        created_at=post.created_at,
        updated_at=post.updated_at,
        images=[PostImageResponse.model_validate(img) for img in post.images],
        comment_count=comment_count,
    )


# =========================================================================
# DELETE /posts/{post_id} —— 删除帖子
# =========================================================================
# 需要登录 + 只能是作者本人操作
# 删除帖子时，同时删除磁盘上的图片文件（数据一致性）

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除帖子（需登录，仅限作者）。

    返回 204 No Content（没有响应 body）。
    删除时同时清理磁盘上的图片文件，防止磁盘垃圾堆积。
    """
    post = await _get_post_or_404(post_id, db)

    # 权限检查
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的帖子")

    # 先删除磁盘上的图片文件
    # 为什么不在 DB 里设 CASCADE + 用定时任务清理？
    #   1. 简单直接，出错容易排查
    #   2. 小项目不需要定时任务
    #   3. os.path.exists() + try/except 保证即使文件已被删也不会崩溃
    for image in post.images:
        file_path = os.path.join(UPLOAD_DIR, image.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    # 删除数据库记录（ORM 级联会自动删除 post_images 和 comments 记录）
    await db.delete(post)
    await db.commit()
    # 204 状态码意味着不返回任何内容


# =========================================================================
# 评论相关端点
# =========================================================================

# ── POST /posts/{post_id}/comments —— 添加评论 ──────────────

@router.post(
    "/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    post_id: int,
    payload: CommentCreate,  # JSON body: {"content": "好帖！"}
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为帖子添加评论（需登录）"""
    # 确保帖子存在（不存在会返回 404）
    await _get_post_or_404(post_id, db)

    # 创建评论记录
    comment = Comment(
        content=payload.content,
        user_id=current_user.id,
        post_id=post_id,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # 再查一次，加载 user 关联（为了在响应里显示评论者的用户名）
    # 为什么不直接用上面的 comment 对象？
    #   上面的 comment 只有 id/content/user_id/post_id（刚插入的值）
    #   comment.user 是空的，需要重新查询 + joinedload 才能拿到 User 对象
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
    )


# ── GET /posts/{post_id}/comments —— 评论列表 ──────────────

@router.get("/{post_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    post_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取帖子的评论列表（公开）"""
    # 确认帖子存在
    await _get_post_or_404(post_id, db)

    # 查所有评论，按时间正序（最早的在前）
    # joinedload(Comment.user)：同时查出评论者信息
    result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.unique().scalars().all()

    # 列表推导式构造响应
    return [
        CommentResponse(
            id=c.id,
            content=c.content,
            user=c.user,
            created_at=c.created_at,
        )
        for c in comments
    ]


# =========================================================================
# 图片相关
# =========================================================================

async def _save_image(post_id: int, file: UploadFile, db: AsyncSession) -> PostImage:
    """
    保存上传的图片文件（内部函数，不是 API 端点）

    做了两件事：
      1. 把文件写入磁盘（app/uploads/<uuid>.png）
      2. 把文件信息写入数据库（post_images 表）

    参数：
      post_id: 图片所属帖子 ID
      file:    FastAPI 的 UploadFile 对象（.filename, .read()）
      db:      数据库会话

    为什么文件名用 UUID？
      如果用户上传 "图片.png"，另一个用户也上传 "图片.png" → 冲突
      UUID 是全局唯一的随机字符串 → 几乎不可能冲突
      例如：cc997a6329ec4863983797a058ba8461.png
    """
    # 提取扩展名（如 .png, .jpg）
    # os.path.splitext("photo.png") → ("photo", ".png")
    ext = os.path.splitext(file.filename or ".png")[1] or ".png"

    # 生成唯一文件名：32 位随机十六进制 + 原扩展名
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # 写入磁盘
    # await file.read() : 异步读取上传文件的全部内容（大文件应改用流式写入）
    # open(file_path, "wb") : wb = 写模式 + 二进制（图片不是文本）
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 写入数据库（元数据：文件名 + 访问路径）
    # url 格式：/static/uploads/<uuid>.png
    #   前端用 http://127.0.0.1:8000 + 这个路径就能访问图片
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


# ── POST /posts/{post_id}/images —— 追加图片 ──────────────

@router.post("/{post_id}/images", response_model=list[PostImageResponse])
async def upload_images(
    post_id: int,
    files: list[UploadFile] = File(...),  # ... = 必填（至少上传一张）
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为已有帖子追加图片（需登录，仅限作者）"""
    post = await _get_post_or_404(post_id, db)

    # 权限检查
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能给自己的帖子上传图片")

    # 逐个处理上传的文件
    images = []
    for file in files:
        if not file.filename:
            continue
        image = await _save_image(post_id, file, db)
        images.append(PostImageResponse.model_validate(image))

    return images
