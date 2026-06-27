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
from app.schemas import (
    CommentCreate,
    CommentResponse,
    PostCreate,
    PostImageResponse,
    PostListResponse,
    PostResponse,
    PostUpdate,
)

router = APIRouter(prefix="/posts", tags=["posts"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── helper ────────────────────────────────────────────────

async def _get_post_or_404(post_id: int, db: AsyncSession) -> Post:
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
    result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post_id)
    )
    return result.scalar() or 0


# ── posts CRUD ─────────────────────────────────────────────

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    title: str = Form(..., min_length=1, max_length=100),
    content: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建帖子（需登录），支持同时上传多张图片"""
    post = Post(
        title=title,
        content=content,
        user_id=current_user.id,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # 处理图片上传
    images: list[PostImageResponse] = []
    if files:
        for file in files:
            if not file.filename:
                continue
            image = await _save_image(post.id, file, db)
            images.append(PostImageResponse.model_validate(image))

    # 重新加载带关联数据的 post
    post = await _get_post_or_404(post.id, db)

    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        user=post.user,
        created_at=post.created_at,
        updated_at=post.updated_at,
        images=images,
        comment_count=0,
    )


@router.get("/", response_model=PostListResponse)
async def list_posts(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取帖子列表（公开，支持分页）"""
    # 总数
    total_result = await db.execute(select(func.count(Post.id)))
    total = total_result.scalar() or 0

    # 帖子列表
    result = await db.execute(
        select(Post)
        .options(joinedload(Post.user), joinedload(Post.images))
        .order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    posts = result.unique().scalars().all()

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


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取帖子详情（公开，含评论列表）"""
    post = await _get_post_or_404(post_id, db)
    comment_count = await _count_comments(post_id, db)

    # 加载评论
    comments_result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    comments = comments_result.unique().scalars().all()

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


@router.put("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    payload: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新帖子（需登录，仅限作者）"""
    post = await _get_post_or_404(post_id, db)

    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改自己的帖子")

    if payload.title is not None:
        post.title = payload.title
    if payload.content is not None:
        post.content = payload.content

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


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除帖子（需登录，仅限作者）"""
    post = await _get_post_or_404(post_id, db)

    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的帖子")

    # 删除关联的图片文件
    for image in post.images:
        file_path = os.path.join(UPLOAD_DIR, image.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    await db.delete(post)
    await db.commit()


# ── comments ───────────────────────────────────────────────

@router.post("/{post_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(
    post_id: int,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加评论（需登录）"""
    # 确保帖子存在
    await _get_post_or_404(post_id, db)

    comment = Comment(
        content=payload.content,
        user_id=current_user.id,
        post_id=post_id,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # 加载用户信息
    result = await db.execute(
        select(Comment).options(joinedload(Comment.user)).where(Comment.id == comment.id)
    )
    comment = result.unique().scalar_one()

    return CommentResponse(
        id=comment.id,
        content=comment.content,
        user=comment.user,
        created_at=comment.created_at,
    )


@router.get("/{post_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    post_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取帖子的评论列表（公开）"""
    await _get_post_or_404(post_id, db)

    result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.unique().scalars().all()

    return [
        CommentResponse(
            id=c.id,
            content=c.content,
            user=c.user,
            created_at=c.created_at,
        )
        for c in comments
    ]


# ── image upload ───────────────────────────────────────────

async def _save_image(post_id: int, file: UploadFile, db: AsyncSession) -> PostImage:
    """保存上传的图片文件并写入数据库记录"""
    # 生成唯一文件名
    ext = os.path.splitext(file.filename or ".png")[1] or ".png"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # 写入磁盘
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 数据库记录
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


@router.post("/{post_id}/images", response_model=list[PostImageResponse])
async def upload_images(
    post_id: int,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为帖子追加图片（需登录，仅限作者）"""
    post = await _get_post_or_404(post_id, db)

    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能给自己的帖子上传图片")

    images = []
    for file in files:
        if not file.filename:
            continue
        image = await _save_image(post_id, file, db)
        images.append(PostImageResponse.model_validate(image))

    return images
