"""
=============================================================================
 models.py —— ORM 数据库模型（Django 的 models.py 对应物）
=============================================================================

Django 对比：
   Django ORM:                          SQLAlchemy 2.0 (async):
   ─────────────                        ──────────────────────
   class User(models.Model):            class User(Base):
       username = models.CharField(         username: Mapped[str] = mapped_column(
           max_length=50,                       String(50), unique=True,
           unique=True,                         index=True
           db_index=True                    )
       )                               → 字段定义语法不同，但语义一样
       posts = models.related_name()       posts = relationship("Post", ...)
                                       → 关联关系定义方式不同，但 ORM 行为一样

   User.objects.filter(id=1)           select(User).where(User.id == 1)
   User.objects.all()                  select(User)
   user.posts.all()                    user.posts（直接访问属性）

SQLAlchemy 2.0 的 Mapped + mapped_column 语法：
   Mapped[int]         : Python 类型注解 = 这个字段在 Python 里是 int
   mapped_column(...)  : 数据库列定义 = 这个字段在 MySQL 里是什么类型
   两个一起用是 SQLAlchemy 2.0 推荐的新写法，比旧版更清晰、IDE 提示更好

时间处理：
   所有时间都用 UTC（timezone.utc），不依赖服务器时区
   Django 也是推荐 UTC（settings.TIME_ZONE = 'UTC'）

v2.0 新增模型：
   - User: 扩展 bio, avatar_url, is_admin 字段
   - Post: 扩展 is_pinned, is_featured, view_count 字段 + category/tag 关联
   - Comment: 扩展 parent_id（嵌套回复）
   - PostLike, PostFavorite: 点赞/收藏关联表
   - Category, Tag, post_tags: 分类/标签系统
   - Notification: 通知系统
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base  # 我们的基类，相当于 Django 的 models.Model


# =========================================================================
# 多对多关联中间表（Django 的 ManyToManyField 自动生成的 through 表）
# =========================================================================
# 为什么手动创建中间表而不是用 Django 风格的 ManyToManyField？
#   1. SQLAlchemy 的 M2M 需要显式定义中间表或使用 secondary 参数
#   2. 手动定义可以加额外字段（如 created_at 创建时间）
#   3. 更灵活：可以指定复合主键、索引
#
# Django 对比：
#   class Post(models.Model):
#       tags = models.ManyToManyField(Tag)  # Django 自动创建 post_tags 中间表

# 帖子-标签 多对多关联表
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    # Django 对比：Django 的 through 表会自动加这两个 FK，这里手动声明
)


# =========================================================================
# User —— 用户模型（Django 的 User 模型对应物）
# =========================================================================
class User(Base):
    __tablename__ = "users"  # Django 会自动生成表名（app_label_modelname），这里手动指定

    # ── 基本字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    # password_hash: bcrypt 输出约 60 字符，255 给足够余量
    # 旧版是 String(64) 存 SHA-256，升级为 255 存 bcrypt
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── v2.0 新增：用户扩展字段 ──────────────────────────
    # bio: 个人简介，最长 500 字符，可为空
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # avatar_url: 头像图片的访问路径（如 /static/uploads/avatars/xxx.png）
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # is_admin: 管理员标志，默认 False
    # Django 对比：Django User 模型的 is_staff / is_superuser
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── 关联关系 ──────────────────────────────────────────
    # relationship 定义了 Python 层面的"对象引用"，不是数据库列！
    # 用法：user.posts → 自动查询这个用户的所有帖子
    #
    # back_populates="user" : 双向关联 —— Post 模型里也必须有一个叫 "user" 的 relationship
    #   （告诉 SQLAlchemy："User 的 posts 和 Post 的 user 是同一对关系的两端"）
    #
    # cascade="all, delete-orphan" :
    #   - 删除用户时，自动删除他的所有帖子和评论
    #   - "delete-orphan"：如果把帖子从 user.posts 里移除，会自动删除帖子
    #   （Django 的 on_delete=models.CASCADE 类似，但 SQLAlchemy 在 ORM 层处理）
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    likes = relationship("PostLike", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("PostFavorite", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


# =========================================================================
# Post —— 帖子模型
# =========================================================================
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    # ── v2.0 新增：帖子扩展字段 ──────────────────────────
    # view_count: 浏览次数（每访问一次帖子详情 +1）
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # is_pinned: 置顶帖子（管理员可设），列表排在前面
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # is_featured: 精华帖子（管理员可设），仅次于置顶
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # category_id: 所属分类的外键（可为空）
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True,
    )

    # ── 时间字段 ──────────────────────────────────────────
    # default=lambda: datetime.now(timezone.utc) :
    #   为什么用 lambda 而不是直接 datetime.now(timezone.utc)？
    #   直接调用会把"导入这个文件的时间"作为默认值，所有帖子都是同一天！
    #   lambda 让每次插入新行时才执行，每个帖子有自己的创建时间
    #
    # onupdate=lambda: datetime.now(timezone.utc) :
    #   每次 UPDATE 时自动更新这个字段，不需要手动设置
    #   Django 的 auto_now=True 对应物
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── 关联关系 ──────────────────────────────────────────
    # post.user        → 帖子的作者（User 对象）
    # post.comments    → 帖子的所有评论（Comment 对象列表）
    # post.images      → 帖子的所有图片（PostImage 对象列表）
    # post.likes       → 帖子的点赞记录
    # post.favorites   → 帖子的收藏记录
    # post.tags        → 帖子的标签（多对多）
    user = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    images = relationship("PostImage", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    favorites = relationship("PostFavorite", back_populates="post", cascade="all, delete-orphan")
    category = relationship("Category", back_populates="posts")
    tags = relationship("Tag", secondary=post_tags, back_populates="posts")


# =========================================================================
# Comment —— 评论模型
# =========================================================================
class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    # ── v2.0 新增：嵌套回复 ──────────────────────────────
    # parent_id: 回复的父评论 ID（自引用外键，指向同表的另一行）
    #   parent_id 为 NULL → 顶级评论（直接回复帖子）
    #   parent_id 不为空 → 回复某条评论（楼中楼）
    # Django 对比：Django-mptt 或 django-treebeard 的 parent 字段
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comments.id"), nullable=True, index=True,
    )

    # ── 关联关系 ──────────────────────────────────────────
    # comment.user   → 评论的作者
    # comment.post   → 评论所属的帖子
    # comment.parent → 父评论（被回复的那条）
    # comment.replies → 子评论列表（所有回复这条的评论）
    user = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")
    # 自引用关系：remote_side 指定哪一边是"被引用方"（父评论）
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship(
        "Comment", back_populates="parent", cascade="all, delete-orphan",
    )


# =========================================================================
# PostImage —— 帖子图片模型
# =========================================================================
# 为什么图片单独一张表而不是 Post 的一个字段？
#   1. 一个帖子可能有多张图片（一对多关系）
#   2. 分离后可以单独查询图片、单独删除某张图片
#   3. 符合数据库范式——不要把列表塞进一个字段里
class PostImage(Base):
    __tablename__ = "post_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    post = relationship("Post", back_populates="images")


# =========================================================================
# v2.0 新增：PostLike —— 点赞关联表
# =========================================================================
# 为什么点赞单独一张表？
#   1. 点赞是一个"用户-帖子"的多对多关系（一个用户可以赞多个帖子，一个帖子可以被多个用户赞）
#   2. 独立表可以存点赞时间、做唯一约束（一个人不能重复赞同一个帖子）
#   3. Django 对比：类似 Django 的 ManyToManyField through 表
class PostLike(Base):
    __tablename__ = "post_likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")


# =========================================================================
# v2.0 新增：PostFavorite —— 收藏关联表
# =========================================================================
# 与 PostLike 完全一样的结构，只是语义不同（收藏 vs 点赞）
# 为什么不合并成一张表加 type 字段？
#   1. 语义清晰：点赞和收藏是不同的操作
#   2. 独立查询：我要看"我的收藏"不需要过滤 type
#   3. 前端 UI 独立："点赞"按钮和"收藏"按钮互不影响
class PostFavorite(Base):
    __tablename__ = "post_favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    user = relationship("User", back_populates="favorites")
    post = relationship("Post", back_populates="favorites")


# =========================================================================
# v2.0 新增：Category —— 帖子分类
# =========================================================================
# Django 对比：Django 的 Category 模型
# 分类是预定义的一组选项（如"技术"、"生活"、"问答"），由管理员创建
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    posts = relationship("Post", back_populates="category")


# =========================================================================
# v2.0 新增：Tag —— 帖子标签
# =========================================================================
# Django 对比：Django 的 Tag 模型（通常用 django-taggit 包实现）
# 标签更灵活，任何人都可以用任意标签，类似 Twitter 的 hashtag
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    posts = relationship("Post", secondary=post_tags, back_populates="tags")


# =========================================================================
# v2.0 新增：Notification —— 通知
# =========================================================================
# 通知类型说明：
#   like     → 有人点赞了你的帖子
#   comment  → 有人评论了你的帖子
#   reply    → 有人回复了你的评论
#   system   → 系统通知（如帖子被设为精华）
#
# Django 对比：类似 django-notifications 包的通知模型
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )
    # 通知类型：like / comment / reply / system
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 通知内容文案（如 "张三 点赞了你的帖子「FastAPI 入门指南」"）
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    # is_read: 是否已读
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 关联的帖子 ID（点击通知可以跳转到对应帖子）
    related_post_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=True,
    )
    # 关联的评论 ID（用于评论/回复类型通知）
    related_comment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comments.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    user = relationship("User", back_populates="notifications")
    related_post = relationship("Post")
    related_comment = relationship("Comment")