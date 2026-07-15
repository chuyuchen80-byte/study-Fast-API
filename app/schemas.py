"""
=============================================================================
 schemas.py —— Pydantic 数据模型（Django Forms + DRF Serializer 对应物）
=============================================================================

Django 对比：
   Django 的请求校验主要有两种方式：
     1. Django Forms：form = UserRegisterForm(request.POST); form.is_valid()
     2. DRF Serializer：serializer = UserSerializer(data=request.data)

   FastAPI 用 Pydantic 统一做三件事：
     1. 请求数据校验    —— 相当于 forms.py / DRF Serializer 的 validate
     2. 自动生成文档    —— 相当于 drf-spectacular 做的 OpenAPI schema
     3. 响应数据序列化  —— 相当于 DRF Serializer 的 .data / to_representation

Pydantic 的两个核心概念：
   BaseModel : 定义一个数据模型（类似 DRF 的 Serializer）
   Field()   : 字段校验规则（min_length, max_length, description 等）
              Django 对比：Field() ≈ forms.CharField(max_length=..., min_length=...)

ConfigDict(from_attributes=True)：
   告诉 Pydantic "这个模型可以从 ORM 对象转换"
   以前叫 class Config: orm_mode = True（Pydantic v1 语法）
   有了它，UserResponse.model_validate(user_orm_instance) 才能工作
   相当于 DRF 的 class Meta: model = User

v2.0 新增 Schema：
   用户：UserUpdate, PasswordUpdate, UserProfileResponse
   帖子：PostResponse 扩展 like_count/favorite_count/is_liked/is_favorited/view_count/category/tags
   评论：CommentUpdate
   分类/标签：CategoryResponse, TagResponse
   通知：NotificationResponse
   Token：扩展 refresh_token，新增 TokenRefreshRequest
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# =========================================================================
# 用户相关 Schema
# =========================================================================

class UserRegister(BaseModel):
    """注册请求：前端 POST /user/register 时发送的 JSON body"""
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=50)


class UserLogin(BaseModel):
    """登录请求：前端 POST /user/login 时发送的 JSON body"""
    username: str
    password: str


class UserResponse(BaseModel):
    """
    用户信息响应：返回给前端的用户数据（v2.0 扩展了 bio/avatar/is_admin）

    from_attributes=True → 可以从 ORM 对象直接构造
    UserResponse.model_validate(user_orm_instance) ✓
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    bio: str | None = None
    avatar_url: str | None = None
    is_admin: bool = False
    # 注意：这里故意没有 password_hash 字段 —— 密码哈希绝不返回给前端！
    # Django 对比：DRF Serializer 里不写 password 字段即可


class UserUpdate(BaseModel):
    """
    更新用户资料请求：PUT /user/me 的 JSON body

    所有字段都是 Optional = 只传要改的字段
    Django 对比：类似 Django 的 UserChangeForm
    """
    username: str | None = Field(None, min_length=3, max_length=50)
    bio: str | None = Field(None, max_length=500)


class PasswordUpdate(BaseModel):
    """
    修改密码请求：PUT /user/me/password 的 JSON body

    需要提供旧密码验证身份（防止别人在你离开时改你的密码）
    Django 对比：Django 的 PasswordChangeForm
    """
    old_password: str
    new_password: str = Field(min_length=6, max_length=50)


class UserProfileResponse(BaseModel):
    """
    用户公开资料响应：GET /user/{id} 的返回（含用户统计信息）

    比 UserResponse 多了统计数据，用于个人主页展示
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    bio: str | None = None
    avatar_url: str | None = None
    is_admin: bool = False
    post_count: int = 0
    comment_count: int = 0


# v2.0 Bugfix: 前端 UserProfileView 期望 { user, posts, total } 嵌套结构
# UserProfileResponse 只能做顶层响应，嵌套场景需要包装 Schema
class UserProfileDetailResponse(BaseModel):
    """用户主页完整响应：用户资料 + 帖子列表（分页）"""
    user: UserProfileResponse
    posts: list["PostResponse"] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class Token(BaseModel):
    """
    登录成功后的响应：JWT access_token + refresh_token + 用户信息

    v2.0 新增 refresh_token 字段（向后兼容：旧前端会忽略这个字段）
    Django 对比：DRF Simple JWT 的 TokenObtainPairResponse
    """
    access_token: str                        # JWT 访问令牌
    refresh_token: str = ""                 # JWT 刷新令牌（v2.0 新增）
    token_type: str = "bearer"              # 固定值 "bearer"（OAuth2 规范）
    user: UserResponse | None = None        # 当前用户信息（可选）
    message: str | None = None              # 提示消息


class TokenRefreshRequest(BaseModel):
    """刷新令牌请求：POST /user/refresh 的 JSON body"""
    refresh_token: str


class TokenData(BaseModel):
    """JWT 解码后的 payload 数据结构（内部使用，不暴露给前端）"""
    username: str | None = None


# =========================================================================
# 帖子相关 Schema
# =========================================================================

class PostUpdate(BaseModel):
    """
    更新帖子请求：PUT /posts/{id} 的 JSON body

    所有字段都是 Optional（None = "不修改这个字段"）
    v2.0 新增：category_id（分类ID）、tags（逗号分隔的标签名）
    """
    title: str | None = Field(None, min_length=1, max_length=100)
    content: str | None = None
    category_id: int | None = None
    tags: str | None = Field(None, description="逗号分隔的标签名，如 'python,fastapi,教程'")


class PostImageResponse(BaseModel):
    """图片信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str   # 磁盘文件名
    url: str        # 访问 URL（/static/uploads/xxx.png）


class CategoryResponse(BaseModel):
    """分类信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class TagResponse(BaseModel):
    """标签信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PostResponse(BaseModel):
    """
    帖子详情/列表中的单个帖子响应（v2.0 大幅扩展）

    所有 ORM 字段可通过 from_attributes 自动映射，
    计算字段（like_count、is_liked 等）由路由函数手动设置
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    user: UserResponse                      # 嵌套对象：把作者信息嵌在里面
    created_at: datetime
    updated_at: datetime
    images: list[PostImageResponse] = []    # 嵌套列表：帖子的所有图片
    comment_count: int = 0                  # 评论总数（非 ORM 字段，路由中计算）
    # ── v2.0 新增字段 ─────────────────────────────────────
    view_count: int = 0                     # 浏览次数
    like_count: int = 0                     # 点赞总数（非 ORM 字段，路由中计算）
    favorite_count: int = 0                 # 收藏总数（非 ORM 字段，路由中计算）
    is_liked: bool = False                  # 当前用户是否已点赞（需登录）
    is_favorited: bool = False              # 当前用户是否已收藏（需登录）
    is_pinned: bool = False                 # 是否置顶
    is_featured: bool = False               # 是否精华
    category: CategoryResponse | None = None  # 所属分类
    tags: list[TagResponse] = []            # 标签列表


class PostListResponse(BaseModel):
    """帖子列表响应（含分页信息）"""
    posts: list[PostResponse]   # 当前页的帖子
    total: int                  # 全部帖子总数（前端用来算"共 X 条"和总页数）
    page: int                   # 当前页码
    page_size: int              # 每页条数


# =========================================================================
# 评论相关 Schema
# =========================================================================

class CommentCreate(BaseModel):
    """
    添加评论请求：POST /posts/{id}/comments 的 JSON body

    v2.0 新增：parent_id（回复评论时传入被回复评论的 ID）
    """
    content: str = Field(min_length=1, max_length=1000, description="评论内容")
    parent_id: int | None = Field(None, description="回复某条评论时传入该评论的 ID")


class CommentUpdate(BaseModel):
    """
    编辑评论请求：PUT /posts/{pid}/comments/{cid} 的 JSON body（v2.0 新增）
    """
    content: str = Field(min_length=1, max_length=1000, description="修改后的评论内容")


class CommentResponse(BaseModel):
    """
    评论响应（v2.0 扩展：支持嵌套回复）

    递归结构：replies 字段包含子评论列表
    Pydantic 支持自引用类型 —— 在 from __future__ import annotations 后可用
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    user: UserResponse           # 嵌套：评论的作者信息
    created_at: datetime
    parent_id: int | None = None  # 父评论 ID（顶级评论为 None）
    replies: list["CommentResponse"] = []  # 嵌套子评论列表（v2.0 新增）


# =========================================================================
# 点赞/收藏相关 Schema（v2.0 新增）
# =========================================================================

class ToggleResponse(BaseModel):
    """点赞/收藏开关操作的响应"""
    active: bool  # true = 已点赞/已收藏, false = 已取消
    count: int = 0  # 操作后的总点赞/收藏数


# =========================================================================
# 通知相关 Schema（v2.0 新增）
# =========================================================================

class NotificationResponse(BaseModel):
    """通知响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str              # 通知类型：like / comment / reply / system
    message: str           # 通知文案
    is_read: bool          # 是否已读
    related_post_id: int | None = None     # 关联帖子 ID
    related_comment_id: int | None = None  # 关联评论 ID
    created_at: datetime


class NotificationListResponse(BaseModel):
    """通知列表响应（含分页信息）"""
    notifications: list[NotificationResponse]
    total: int
    unread_count: int  # 未读通知数
    page: int
    page_size: int


# =========================================================================
# 分类/标签请求 Schema（v2.0 新增）
# =========================================================================

class CategoryCreate(BaseModel):
    """创建分类请求（管理员操作）"""
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(None, max_length=200)


class TagCreate(BaseModel):
    """创建标签请求"""
    name: str = Field(min_length=1, max_length=50)