# FastAPI 学习指南 — Django 开发者视角

> 本文档面向有 Django 经验的开发者，用 Django 概念类比解释 FastAPI。

---

## 目录

1. [核心概念对比表](#1-核心概念对比表)
2. [项目启动与运行](#2-项目启动与运行)
3. [请求生命周期（完整链路）](#3-请求生命周期)
4. [路由系统](#4-路由系统)
5. [请求数据校验](#5-请求数据校验)
6. [依赖注入（Depends）](#6-依赖注入depends--fastapi-最核心的概念)
7. [数据库操作（SQLAlchemy async）](#7-数据库操作sqlalchemy-async)
8. [认证系统（JWT）](#8-认证系统jwt)
9. [静态文件与文件上传](#9-静态文件与文件上传)
10. [常见问题 FAQ](#10-常见问题-faq)

---

## 1. 核心概念对比表

| 职责 | Django | FastAPI（本项目） |
|------|--------|-------------------|
| 全局配置 | `settings.py` | [config.py](app/config.py) |
| 应用入口 | `wsgi.py` / `asgi.py` | [main.py](app/main.py) — `app = FastAPI()` |
| URL 分发 | `urls.py` + `include()` | `APIRouter` + `app.include_router()` |
| 视图逻辑 | `views.py` 函数 / 类 | `routers/*.py` 里的 `async def` 函数 |
| 请求校验 | `forms.py` / DRF Serializer | Pydantic `BaseModel`（[schemas.py](app/schemas.py)） |
| ORM 模型 | `models.py` + `models.Model` | `models.py` + SQLAlchemy `Base`（[models.py](app/models.py)） |
| 数据库会话 | `request.db` / 自动管理 | `Depends(get_db)` — 手动依赖注入 |
| 要求登录 | `@login_required` | `Depends(get_current_user)` |
| 获取用户 | `request.user` | `current_user = Depends(get_current_user)` |
| 密码处理 | `make_password()` / `check_password()` | `hash_password()` — [auth.py](app/auth.py) |
| JWT 签发 | DRF SimpleJWT | `create_access_token()` — [auth.py](app/auth.py) |
| 中间件 | `MIDDLEWARE` 列表 | `app.add_middleware()` |
| 静态文件 | `STATIC_URL` + `STATIC_ROOT` | `app.mount()` + `StaticFiles` |
| 自动建表 | `python manage.py migrate` | `Base.metadata.create_all()`（启动时） |
| 启动服务器 | `python manage.py runserver` | `uvicorn app.main:app --reload` |
| API 文档 | 无（需要 drf-spectacular） | 自带 `/docs`（Swagger UI）|

---

## 2. 项目启动与运行

### Django 的启动方式

```bash
# Django — 一个命令搞定
python manage.py runserver
```

### FastAPI 的启动方式

```bash
# 进入后端目录
cd fastapi_blog

# 安装依赖
pip install -r requirements.txt

# 启动（--reload = 热重载，改代码自动重启）
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**命令拆解**：

```
uvicorn app.main:app --reload
  ↑      ↑    ↑  ↑     ↑
  │      │    │  │     └─ 热重载（开发用，等同于 Django 的 runserver 自动重载）
  │      │    │  └─────── 变量名（FastAPI() 实例的变量名）
  │      │    └────────── Python 模块路径（app/main.py）
  │      └─────────────── 模块路径 = app 包下的 main 模块
  └────────────────────── ASGI 服务器（Django 用 WSGI 的 Gunicorn/uWSGI）
```

**跟 Django 的区别**：
- Django 自带服务器；FastAPI 用第三方 Uvicorn（更专业、更快的 ASGI 服务器）
- 没有 `manage.py`，没有管理命令，一切都通过 Python 代码或命令行控制

---

## 3. 请求生命周期（完整链路）

以「用户查看帖子详情 `GET /posts/42`」为例：

```
浏览器发送请求 GET http://127.0.0.1:8000/posts/42
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  步骤 1：CORSMiddleware                                │
│  检查请求来源是否在 allow_origins 列表中                │
│  如果是跨域请求 → 添加 Access-Control-* 响应头         │
│  Django 对比：django-cors-headers 中间件                │
└──────────────────┬─────────────────────────────────────┘
                   ▼
┌────────────────────────────────────────────────────────┐
│  步骤 2：路由匹配                                       │
│  app.include_router(posts_router) 注册了 /posts 前缀    │
│  posts_router 里 @router.get("/{post_id}") 匹配 /42     │
│  完整路径 = "/posts" + "/{post_id}" = "/posts/{post_id}"│
│  Django 对比：urlpatterns 里的正则匹配                  │
└──────────────────┬─────────────────────────────────────┘
                   ▼
┌────────────────────────────────────────────────────────┐
│  步骤 3：依赖注入（Depends）                            │
│  get_post(post_id: int, db = Depends(get_db))          │
│  ① post_id = 42（从 URL 提取并转为 int）               │
│  ② db = await get_db().__anext__()  → 数据库会话        │
│  Django 对比：request 对象自动创建，不需要显式注入       │
└──────────────────┬─────────────────────────────────────┘
                   ▼
┌────────────────────────────────────────────────────────┐
│  步骤 4：函数体执行                                     │
│  post = await _get_post_or_404(42, db)                 │
│  → SELECT * FROM posts JOIN users JOIN post_images      │
│  comment_count = await _count_comments(42, db)         │
│  → SELECT COUNT(*) FROM comments WHERE post_id = 42    │
│  Django 对比：views.py 函数体                           │
└──────────────────┬─────────────────────────────────────┘
                   ▼
┌────────────────────────────────────────────────────────┐
│  步骤 5：响应序列化                                     │
│  response_model=PostResponse 告诉 FastAPI 用 Pydantic   │
│  把返回对象转为 JSON                                    │
│  id/username → JSON 原样输出；password_hash → 自动跳过  │
│  Django 对比：DRF Serializer.to_representation()        │
└──────────────────┬─────────────────────────────────────┘
                   ▼
┌────────────────────────────────────────────────────────┐
│  步骤 6：数据库会话自动关闭                              │
│  get_db() 的 finally 块 → session.close()               │
│  Django 对比：请求结束时的自动清理                       │
└──────────────────┬─────────────────────────────────────┘
                   ▼
            返回 JSON 响应给浏览器
```

**关键区别**：Django 很多步骤是框架自动做的（request 创建、DB 会话管理）；FastAPI 更透明，每一步发生了什么都能看到。

---

## 4. 路由系统

### Django 的路由

```python
# urls.py
from django.urls import path, include
from . import views

urlpatterns = [
    path('user/', include('user.urls')),       # 挂载子路由
    path('posts/<int:id>/', views.post_detail),  # 具体路由
]

# user/urls.py
urlpatterns = [
    path('register/', views.register),
    path('login/', views.login),
]
```

### FastAPI 的路由（本项目）

```python
# main.py — 相当于 Django 的根 urls.py
from app.routers.users import router as users_router
from app.routers.posts import router as posts_router

app.include_router(users_router)   # 挂载 /user/* 路由
app.include_router(posts_router)   # 挂载 /posts/* 路由

# routers/users.py — 相当于 Django 的 user/urls.py + user/views.py 合并
router = APIRouter(prefix="/user", tags=["users"])

@router.post("/register")   # 路径 = prefix + "/register" = "/user/register"
async def register(user: UserRegister, db = Depends(get_db)):
    ...

@router.post("/login")      # 路径 = "/user/login"
async def login(user: UserLogin, db = Depends(get_db)):
    ...
```

**FastAPI 的设计哲学**：路由定义和视图逻辑在同一个文件里，不像 Django 需要来回跳转 `urls.py` → `views.py`。

---

## 5. 请求数据校验

### Django 方式

```python
# forms.py
class PostForm(forms.Form):
    title = forms.CharField(min_length=1, max_length=100)
    content = forms.CharField(min_length=1)

# views.py
def create_post(request):
    form = PostForm(request.POST)
    if form.is_valid():
        title = form.cleaned_data['title']
        content = form.cleaned_data['content']
        ...
```

### FastAPI 方式（Pydantic）

```python
# schemas.py
from pydantic import BaseModel, Field

class PostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    content: str | None = None

# routers/posts.py
@router.put("/{post_id}")
async def update_post(
    post_id: int,
    payload: PostUpdate,  # 自动校验！不合法直接返回 422
    ...
):
    # 直接使用 payload.title, payload.content
    # 校验已经由 Pydantic 自动完成
    ...
```

**关键区别**：
- Django 要手动调用 `form.is_valid()` 然后读 `cleaned_data`
- FastAPI 的类型注解 + Pydantic 自动完成校验，不合法请求根本不会进入函数体
- 错误信息自动生成（"title 长度不能超过 100"），会作为 422 响应的 JSON 返回

### 两种接收请求数据的方式

```python
# 方式 1：JSON body（Pydantic 校验）— 适合纯文本数据
@router.post("/posts/")
async def create_post(payload: PostCreate, ...):  # payload 是 Pydantic 对象
    print(payload.title)

# 方式 2：FormData（Form + File）— 适合同时传文本 + 文件
@router.post("/posts/")
async def create_post(
    title: str = Form(...),          # 单个表单字段
    files: list[UploadFile] = File(None),  # 文件字段
    ...
):
    print(title)
```

**为什么不用模型序列化器？**
Django REST Framework 用 Serializer 同时做输入校验和输出序列化；FastAPI 用 Pydantic 也是一个模型同时做这两件事。

---

## 6. 依赖注入（Depends）— FastAPI 最核心的概念

### 什么是依赖注入？

依赖注入就是"一个函数需要的参数，由框架自动提供，不需要手动传"。

### 最简单的例子：获取数据库会话

```python
# 定义一个依赖
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session  # yield = 把 session 交给使用者

# 在路由函数中使用
@router.get("/posts/")
async def list_posts(db: AsyncSession = Depends(get_db)):
    # db 就是 get_db() yield 出来的 session
    # 不需要手动创建，不需要手动关闭
    result = await db.execute(select(Post))
    ...
```

**Django 对比**：Django 的 `request.db` 是框架自动提供的。FastAPI 需要写 `Depends(get_db)`，但你可以控制更多——比如测试时换一个数据库。

### 嵌套依赖（链式调用）

```python
# 依赖 1：从请求头提取 token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login")

# 依赖 2：解密 token → 查用户（底层依赖 oauth2_scheme）
async def get_current_user(
    token: str = Depends(oauth2_scheme),  # 先调用这个
    db: AsyncSession = Depends(get_db),    # 再调用这个
) -> User:
    payload = jwt.decode(token, ...)
    result = await db.execute(select(User).where(...))
    return result.scalar_one()

# 依赖 3：路由使用（底层依赖 get_current_user）
@router.get("/user/me")
async def profile(current_user: User = Depends(get_current_user)):
    # current_user 就是 get_current_user() 返回的 User 对象
    return {"username": current_user.username}
```

**调用链**：
```
请求 → OAuth2PasswordBearer(tokenUrl) → 提取 token 字符串
      → get_current_user(token, db)     → 解密 JWT + 查数据库
      → current_user = User 对象        → 路由函数使用
```

**Django 对比**：
```python
@login_required
def profile(request):
    return JsonResponse({"username": request.user.username})
```

效果一样，但 Depends 更灵活——你可以在任何层级复用、替换、组合依赖。

---

## 7. 数据库操作（SQLAlchemy async）

### 查询对比

```python
# ─── Django ORM ───
users = User.objects.all()
user = User.objects.get(id=1)
user = User.objects.filter(username='zhangsan').first()
posts = Post.objects.select_related('user').prefetch_related('images').all()
count = Comment.objects.filter(post_id=post_id).count()

# ─── SQLAlchemy 2.0 async ───
result = await db.execute(select(User))
users = result.scalars().all()

result = await db.execute(select(User).where(User.id == 1))
user = result.scalar_one_or_none()

result = await db.execute(select(User).where(User.username == 'zhangsan'))
user = result.scalar_one_or_none()

result = await db.execute(
    select(Post)
    .options(joinedload(Post.user), joinedload(Post.images))
)
posts = result.unique().scalars().all()

result = await db.execute(
    select(func.count(Comment.id)).where(Comment.post_id == post_id)
)
count = result.scalar() or 0
```

### 增删改对比

```python
# ─── Django ORM ───
# 创建
user = User.objects.create(username='zhangsan', password_hash='...')

# 更新
user.username = 'new_name'
user.save()

# 删除
user.delete()

# ─── SQLAlchemy 2.0 async ───
# 创建（三步走）
user = User(username='zhangsan', password_hash='...')
db.add(user)
await db.commit()
await db.refresh(user)  # 获取数据库生成的 id

# 更新
user.username = 'new_name'
await db.commit()

# 删除
await db.delete(user)
await db.commit()
```

**关键区别**：
- Django 的 `.save()` / `.create()` 立即执行 SQL
- SQLAlchemy 分两步：`add()`（标记）+ `commit()`（执行）
- SQLAlchemy 需要手动 `commit()`，这给了你做事务控制的能力

### 异步要点

```python
# 所有数据库操作都要 await
result = await db.execute(select(User))    # ✓ 异步
user = result.scalar_one_or_none()         # ✓ 不需要 await（纯 Python 操作）

# 路由函数必须是 async def
@router.get("/posts/")
async def list_posts(...):  # ✓ async def，不是 def
```

---

## 8. 认证系统（JWT）

### Django 的认证流程

```
POST /login（username + password）
      ↓
Django authenticate(username, password)
      ↓
验证通过 → login(request, user) → 设置 session cookie
      ↓
后续请求 → SessionMiddleware 从 cookie 恢复 session → request.user
```

### FastAPI（本项目）的 JWT 认证流程

```
POST /user/login（username + password）
      ↓
hash_password(input_password) == db_user.password_hash
      ↓
验证通过 → create_access_token({"sub": username}) → 返回 JWT 字符串
      ↓
前端存到 localStorage，每次请求带 Authorization: Bearer <token>
      ↓
后续请求 → get_current_user(token, db)
           → jwt.decode(token) 验证签名 + 检查过期
           → 查数据库获取 User 对象
           → current_user 注入路由函数
```

**区别**：
- Django 用 Session（服务端存状态，cookie 存 session_id）
- 本项目用 JWT（服务端不存状态，token 本身包含用户信息）
- JWT 的好处：适合前后端分离、适合分布式部署、服务端不需要共享 session

---

## 9. 静态文件与文件上传

### Django 方式

```python
# settings.py
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# urls.py
from django.conf import settings
from django.conf.urls.static import static
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### FastAPI 方式（本项目）

```python
# config.py
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# main.py
from fastapi.staticfiles import StaticFiles
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
```

**区别**：FastAPI 用 `app.mount()` 更直观（路径 → 目录），但文件上传后需要手动管理元数据（我们存到了 `post_images` 表）。

---

## 10. 常见问题 FAQ

### Q: 为什么所有路由函数都是 `async def`？

因为 SQLAlchemy 的异步操作需要 `await`，而 `await` 只能在 `async def` 函数里使用。

如果不用 async（同步 SQLAlchemy），函数可以写成普通的 `def`。但 async 能处理更多并发请求。

### Q: `await` 到底在等什么？

```
await db.execute(select(User))
```

程序到这里暂停，把线程让给其他请求，等数据库返回结果后再继续。它不是"空等"，是"这期间可以去干别的事"。

**这就是 FastAPI 高性能的原因**：一个线程可以交替处理多个请求，不需要为每个请求开一个线程。

### Q: Pydantic 的 `model_validate()` 是什么？

```python
# ORM 对象 → Pydantic 对象
user_response = UserResponse.model_validate(db_user)

# 等价于 DRF 的
user_response = UserSerializer(db_user).data
```

`from_attributes=True` 配置让 Pydantic 能从 SQLAlchemy ORM 对象的属性读取数据。

### Q: 为什么不用 Django？

Django 适合"全栈一体"的项目（后端 + 模板 + 表单一体），FastAPI 更适合"前后端分离 + API 为主"的项目。

| 特性 | Django | FastAPI |
|------|--------|---------|
| 开发速度 | 快（很多内置功能） | 快（代码少、自动文档） |
| 灵活性 | 中等（框架规范强） | 高（按需组合） |
| 异步支持 | 部分（Django 4.1+） | 原生（基于 Starlette） |
| API 文档 | 需要第三方包 | 自带 /docs |
| 适合场景 | 传统网站、CMS、Admin | 微服务、前后端分离、高并发 API |

### Q: 我该按什么顺序学 FastAPI？

建议按本项目的依赖顺序阅读：

1. **[config.py](app/config.py)** — 最简单的配置
2. **[schemas.py](app/schemas.py)** — Pydantic 模型，理解数据校验
3. **[models.py](app/models.py)** — SQLAlchemy ORM 模型
4. **[database.py](app/database.py)** — 数据库引擎 + 会话管理
5. **[auth.py](app/auth.py)** — JWT 认证逻辑
6. **[routers/users.py](app/routers/users.py)** — 简单路由（CR 操作）
7. **[routers/posts.py](app/routers/posts.py)** — 复杂路由（CRUD + 评论 + 图片）
8. **[main.py](app/main.py)** — 把所有模块拼在一起

每个文件的注释都标注了"**Django 对比**"，对照着看最容易理解。

---

## 附录：本项目完整请求链路图

```
用户：POST /posts/（FormData: title + content + files）
              │
              ▼
┌─ main.py ──────────────────────────────────────────────────┐
│  CORSMiddleware → 通过（来源是 127.0.0.1:5173）             │
│  include_router(posts_router) → 匹配 prefix="/posts"        │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─ routers/posts.py ─────────────────────────────────────────┐
│  @router.post("/") → 完整路径 = /posts/                     │
│                                                             │
│  Depends(get_current_user):                                 │
│    ├─ OAuth2PasswordBearer → 从 Authorization 头拿 token    │
│    ├─ jwt.decode(token) → 验证签名 + 检查过期               │
│    ├─ select(User).where(username=...) → 查数据库           │
│    └─ return User(id=1, username="zhangsan")                │
│                                                             │
│  Depends(get_db):                                           │
│    └─ AsyncSessionLocal() → yield session                   │
│                                                             │
│  函数体:                                                    │
│    ├─ Post(title=..., content=..., user_id=1)              │
│    ├─ db.add(post) → db.commit() → db.refresh(post)        │
│    ├─ for file in files:                                    │
│    │    ├─ uuid.uuid4().hex → 生成唯一文件名                 │
│    │    ├─ await file.read() → 读取文件内容                  │
│    │    ├─ open(path, "wb").write(content) → 写磁盘          │
│    │    └─ PostImage(post_id=1, filename=..., url=...) → DB │
│    └─ return PostResponse(...)                              │
│                                                             │
│  response_model=PostResponse → Pydantic 序列化为 JSON       │
│                                                             │
│  get_db() finally → session.close()                         │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
  返回: { "id": 1, "title": "...", "user": {...}, ... }
```
