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
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# =========================================================================
# 用户相关 Schema
# =========================================================================

class UserRegister(BaseModel):
    """注册请求：前端 POST /user/register 时发送的 JSON body"""
    # Field(min_length=3, max_length=50) 校验规则：
    #   用户名至少 3 个字符，最长 50 个字符
    #   如果校验失败，FastAPI 自动返回 422 错误（带具体原因），不需要手动写 if 判断
    # Django 对比：forms.CharField(min_length=3, max_length=50)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=50)


class UserLogin(BaseModel):
    """登录请求：前端 POST /user/login 时发送的 JSON body"""
    username: str
    password: str


class UserResponse(BaseModel):
    """用户信息响应：返回给前端的用户数据"""
    # from_attributes=True → 可以从 ORM 对象直接构造
    # UserResponse.model_validate(user_orm_instance) ✓
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    # 注意：这里故意没有 password_hash 字段 —— 密码哈希绝不返回给前端！
    # Django 对比：DRF Serializer 里不写 password 字段即可


class Token(BaseModel):
    """登录成功后的响应：JWT token + 用户信息"""
    access_token: str                        # JWT 字符串
    token_type: str = "bearer"             # 固定值 "bearer"（OAuth2 规范）
    user: UserResponse | None = None       # 当前用户信息（可选）
    message: str | None = None             # 提示消息


class TokenData(BaseModel):
    """JWT 解码后的 payload 数据结构（内部使用，不暴露给前端）"""
    username: str | None = None


# =========================================================================
# 帖子相关 Schema
# =========================================================================

class PostUpdate(BaseModel):
    """更新帖子请求：PUT /posts/{id} 的 JSON body
    所有字段都是 Optional（None = "不修改这个字段"）
    为什么不用 PostCreate？
      更新接口可以有单独上传图片的端点，update 只改标题和正文
    """
    title: str | None = Field(None, min_length=1, max_length=100)
    content: str | None = None


class PostImageResponse(BaseModel):
    """图片信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str   # 磁盘文件名
    url: str        # 访问 URL（/static/uploads/xxx.png）


class PostResponse(BaseModel):
    """帖子详情/列表中的单个帖子响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    user: UserResponse                      # 嵌套对象：把作者信息嵌在里面
    created_at: datetime
    updated_at: datetime
    images: list[PostImageResponse] = []    # 嵌套列表：帖子的所有图片
    comment_count: int = 0                  # 评论总数（不返回所有评论内容，只返回数量）


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
    """添加评论请求：POST /posts/{id}/comments 的 JSON body"""
    content: str = Field(min_length=1, max_length=1000, description="评论内容")


class CommentResponse(BaseModel):
    """评论响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    user: UserResponse       # 嵌套：评论的作者信息
    created_at: datetime
