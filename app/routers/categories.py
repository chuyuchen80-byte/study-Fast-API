"""
=============================================================================
 routers/categories.py —— 分类与标签路由（v2.0 新增文件）
=============================================================================

Django 对比：
   Django: CategoryViewSet + TagViewSet（DRF）
   FastAPI: APIRouter 集中管理分类和标签端点

端点一览：
   分类：
     GET  /categories     → 获取所有分类（公开）
     POST /categories     → 创建分类（仅管理员）
   标签：
     GET  /tags           → 搜索/列出标签（支持 ?q= 搜索）
     POST /tags           → 创建标签（需登录）

分类 vs 标签的区别：
   分类（Category）：
     - 预定义的有限选项（如"技术"、"生活"、"问答"）
     - 由管理员创建和管理
     - 一个帖子只能属于一个分类
     - 类似博客的分类目录
   标签（Tag）：
     - 用户自由使用（如 "python", "fastapi", "教程"）
     - 任何人都可以创建新标签（发帖时自动创建）
     - 一个帖子可以有多个标签
     - 类似 Twitter 的 hashtag
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Category, Tag, User
from app.schemas import CategoryCreate, CategoryResponse, TagCreate, TagResponse

# ── Router 定义 ───────────────────────────────────────────
router = APIRouter(tags=["分类与标签"])


# =========================================================================
# 分类端点
# =========================================================================

# ── GET /categories —— 获取所有分类 ──────────────────────

@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
):
    """
    获取所有分类列表（公开接口）。

    v2.0 新增端点。

    返回所有分类，按 ID 正序排列。

    使用场景：
      - 前端下拉框选择分类（发帖时）
      - 导航栏显示分类列表
      - 侧边栏分类筛选

    Django 对比：
      Category.objects.all().order_by('id')
    """
    result = await db.execute(
        select(Category).order_by(Category.id.asc())
    )
    categories = result.scalars().all()
    return [CategoryResponse.model_validate(c) for c in categories]


# ── POST /categories —— 创建分类（仅管理员） ──────────────

@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新分类（仅管理员可操作）。

    v2.0 新增端点。

    权限：仅 is_admin=True 的用户可创建分类。
    分类名必须唯一。

    Django 对比：
      @user_passes_test(lambda u: u.is_staff)
      def create_category(request):
          ...
    """
    # ── 权限检查 ──────────────────────────────────────────
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可创建分类")

    # ── 检查分类名唯一性 ──────────────────────────────────
    result = await db.execute(
        select(Category).where(Category.name == payload.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="分类名已存在")

    # ── 创建分类 ─────────────────────────────────────────
    category = Category(
        name=payload.name,
        description=payload.description,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    return CategoryResponse.model_validate(category)


# =========================================================================
# 标签端点
# =========================================================================

# ── GET /tags —— 搜索/列出标签 ──────────────────────────

@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    q: str | None = Query(None, description="搜索关键词（模糊匹配）"),
    db: AsyncSession = Depends(get_db),
):
    """
    搜索或列出所有标签（公开接口）。

    v2.0 新增端点。

    支持两种模式：
      1. 不带参数 GET /tags          → 返回所有标签
      2. 带参数   GET /tags?q=python → 搜索包含 "python" 的标签（模糊匹配）

    使用场景：
      - 前端输入框自动补全（标签搜索，如 Twitter 的 hashtag 建议）
      - 标签云展示（列出所有标签）

    注意：此端点返回的是 Tag 本身（{id, name}），
    不返回帖子列表。要按标签查帖子用 GET /posts/?tag=python。

    Django 对比：
      Tag.objects.filter(name__icontains=q)  # 搜索
      Tag.objects.all()                      # 列出全部
    """
    query = select(Tag)

    if q and q.strip():
        # 模糊搜索：WHERE name LIKE '%q%'
        query = query.where(Tag.name.contains(q.strip()))

    query = query.order_by(Tag.name.asc())

    result = await db.execute(query)
    tags = result.scalars().all()
    return [TagResponse.model_validate(t) for t in tags]


# ── POST /tags —— 创建标签 ──────────────────────────────

@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新标签（需登录）。

    v2.0 新增端点。

    所有登录用户都可以创建标签（类似 Twitter 的 hashtag 机制）。
    发帖时标签会自动创建（POST /posts/ 的 tags 参数），
    此端点用于手动创建标签（如管理标签列表）。

    标签名必须唯一。

    Django 对比：
      Tag.objects.get_or_create(name=name)
      → 如果存在就返回已有标签，不存在就创建
    """
    # ── 检查标签名唯一性 ──────────────────────────────────
    result = await db.execute(
        select(Tag).where(Tag.name == payload.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="标签名已存在")

    # ── 创建标签 ─────────────────────────────────────────
    tag = Tag(name=payload.name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    return TagResponse.model_validate(tag)