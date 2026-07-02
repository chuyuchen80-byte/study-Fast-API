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
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base  # 我们的基类，相当于 Django 的 models.Model


# =========================================================================
# User —— 用户模型（Django 的 User 模型对应物）
# =========================================================================
class User(Base):
    __tablename__ = "users"  # Django 会自动生成表名（app_label_modelname），这里手动指定

    # ── 字段 ──────────────────────────────────────────────
    # primary_key=True : 主键
    # index=True       : 创建索引（加速 WHERE / JOIN 查询）
    # unique=True      : 唯一约束（用户名不能重复）
    # nullable=False   : 不允许 NULL（默认就是 False，显式写出来更清晰）
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 固定 64 字符

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


# =========================================================================
# Post —— 帖子模型
# =========================================================================
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)          # 标题，最长 100 字符
    content: Mapped[str] = mapped_column(Text, nullable=False)               # Body 用 Text 类型（不限长度）
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)  # 外键 → users 表

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
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── 关联关系 ──────────────────────────────────────────
    # 三个 relationship，分别关联到 User、Comment、PostImage
    # post.user      → 帖子的作者（User 对象）
    # post.comments  → 帖子的所有评论（Comment 对象列表）
    # post.images    → 帖子的所有图片（PostImage 对象列表）
    user = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    images = relationship("PostImage", back_populates="post", cascade="all, delete-orphan")


# =========================================================================
# Comment —— 评论模型
# =========================================================================
class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)   # 谁评论的
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id"), nullable=False)   # 评论哪个帖子
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── 关联关系 ──────────────────────────────────────────
    # comment.user → 评论的作者
    # comment.post → 评论所属的帖子
    user = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")


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
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)     # 磁盘上的文件名（UUID.png）
    url: Mapped[str] = mapped_column(String(500), nullable=False)          # 访问路径（/static/uploads/xxx.png）

    post = relationship("Post", back_populates="images")
