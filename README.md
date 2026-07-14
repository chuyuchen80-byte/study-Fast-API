# FastAPI Blog v2.0 — 全栈论坛系统

基于 **FastAPI + Vue 3** 的全栈论坛项目。v2.0 全面升级：bcrypt密码、双令牌、点赞收藏、分类标签、嵌套评论、通知系统、管理员权限、Markdown渲染、前端 Vue Router + Pinia 重构。

---

## 🏗 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| **后端框架** | FastAPI | 0.136 |
| **ORM** | SQLAlchemy 2.0 (async) | 2.0.50 |
| **数据库** | MySQL (aiomysql) | — |
| **密码哈希** | passlib + bcrypt | 1.7 |
| **认证** | JWT 双令牌 (python-jose) | 3.3.0 |
| **限流** | slowapi | 0.1 |
| **前端框架** | Vue 3 + Vue Router + Pinia | 3.5 |
| **构建工具** | Vite (含代理) | 8.0 |
| **服务器** | Uvicorn | 0.48 |

---

## 📂 项目结构

```
FastAPI/
├── fastapi_blog/                # 后端
│   ├── app/
│   │   ├── config.py            # 统一配置（DB / Auth / Upload）
│   │   ├── main.py              # FastAPI 入口 + CORS + 路由挂载 + 生命周期
│   │   ├── database.py          # 异步引擎 + 会话工厂 + get_db 依赖
│   │   ├── auth.py              # JWT 生成/校验 + get_current_user
│   │   ├── models.py            # ORM 模型：User / Post / Comment / PostImage
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── users.py         # 用户路由：注册 / 登录 / 个人信息
│   │   │   └── posts.py         # 论坛路由：帖子 CRUD / 评论 / 图片
│   │   └── uploads/             # 上传图片存储目录（已 gitignore）
│   ├── .gitignore
│   └── requirements.txt
│
├── frontent/                    # 前端
│   ├── src/
│   │   ├── main.js              # Vue 入口
│   │   ├── App.vue              # 根组件：视图路由 + 认证状态管理
│   │   ├── assets/
│   │   │   └── main.css         # 全局样式（CSS 变量体系）
│   │   └── components/
│   │       ├── ForumList.vue    # 帖子列表（分页）
│   │       ├── PostDetail.vue   # 帖子详情 + 评论
│   │       └── CreatePost.vue   # 创建/编辑帖子 + 图片上传
│   ├── vite.config.js
│   ├── package.json
│   └── .gitignore
│
└── README.md
```

---

## 🚀 功能

### 用户系统
- 注册 `/user/register`
- 登录 `/user/login`（返回 JWT token）
- 获取当前用户信息 `/user/me`
- 用户列表 `/user/list`

### 论坛
- 发布帖子（支持 Markdown 文本 + 多图上传）
- 帖子列表（分页，最新优先）
- 帖子详情（含评论数统计）
- 编辑帖子（仅限作者）
- 删除帖子（仅限作者，自动清理图片文件）

### 评论
- 为帖子添加评论
- 查看帖子的所有评论

### 图片
- 创建帖子时同时上传多张图片
- 为已有帖子追加图片
- UUID 文件名防冲突
- 通过 `/static/uploads/` 提供静态访问

---

## 📡 API 端点

### 用户 — `/user`

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/user/register` | 否 | 注册（username + password） |
| POST | `/user/login` | 否 | 登录，返回 JWT + 用户信息 |
| GET | `/user/me` | 是 | 获取当前登录用户 |
| GET | `/user/list` | 否 | 获取所有用户列表 |

### 帖子 — `/posts`

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/posts/` | 是 | 创建帖子（FormData: title + content + files） |
| GET | `/posts/` | 否 | 帖子列表（?page=1&page_size=20） |
| GET | `/posts/{id}` | 否 | 帖子详情 |
| PUT | `/posts/{id}` | 是 | 更新帖子（仅作者） |
| DELETE | `/posts/{id}` | 是 | 删除帖子 + 图片文件（仅作者） |

### 评论 — `/posts/{id}/comments`

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/posts/{id}/comments` | 是 | 添加评论 |
| GET | `/posts/{id}/comments` | 否 | 获取评论列表 |

### 图片 — `/posts/{id}/images`

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/posts/{id}/images` | 是 | 追加图片（仅作者） |

### 静态文件

| 路径 | 说明 |
|---|---|
| `/static/uploads/{filename}` | 访问上传的图片 |
| `/docs` | Swagger UI（自动生成） |
| `/redoc` | ReDoc 文档 |

---

## 🗄 数据库模型

```
users
├── id (PK, INT)
├── username (VARCHAR 50, UNIQUE)
├── password_hash (VARCHAR 64, SHA-256)
├── posts → [Post]
└── comments → [Comment]

posts
├── id (PK, INT)
├── title (VARCHAR 100)
├── content (TEXT)
├── user_id (FK → users.id)
├── created_at (DATETIME, UTC)
├── updated_at (DATETIME, UTC)
├── user → User
├── comments → [Comment]
└── images → [PostImage]

comments
├── id (PK, INT)
├── content (TEXT)
├── user_id (FK → users.id)
├── post_id (FK → posts.id)
├── created_at (DATETIME, UTC)
├── user → User
└── post → Post

post_images
├── id (PK, INT)
├── post_id (FK → posts.id)
├── filename (VARCHAR 255, UUID + ext)
├── url (VARCHAR 500, /static/uploads/{filename})
└── post → Post
```

---

## 🔧 快速开始

### 环境要求

- **Python** ≥ 3.10
- **Node.js** ≥ 20.19
- **MySQL** 已运行

### 1. 创建数据库

```sql
CREATE DATABASE fast_api_blog DEFAULT CHARACTER SET utf8mb4;
```

### 2. 启动后端

```bash
cd fastapi_blog

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选，不设则使用默认值）
export DATABASE_URL="mysql+aiomysql://root:你的密码@localhost/fast_api_blog?charset=utf8mb4"
export SECRET_KEY="你的密钥"

# 启动服务（表会自动创建）
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. 启动前端

```bash
cd frontent

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 `http://127.0.0.1:5173`

### 4. 验证

```bash
# 后端健康检查
curl http://127.0.0.1:8000/user/list

# API 文档
open http://127.0.0.1:8000/docs
```

---

## ⚙️ 配置

所有配置项集中在 [config.py](fastapi_blog/app/config.py)，支持环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://root:root@localhost/fast_api_blog?charset=utf8mb4` | 数据库连接 |
| `SECRET_KEY` | `fastapi_blog_secret_key` | JWT 签名密钥 |

> **注意**：生产环境务必通过环境变量覆盖默认值，不要将密码和密钥提交到代码仓库。

---

## 🔒 认证流程

1. 客户端发送 `POST /user/login`（username + password）
2. 服务器验证密码（SHA-256 哈希比对），生成 JWT token（HS256，30 分钟过期）
3. 客户端将 token 存入 `Authorization: Bearer <token>` 请求头
4. 需要认证的端点通过 `get_current_user` 依赖校验 token，注入 `current_user`

```
Client                    Server
  │  POST /user/login       │
  │ ──────────────────────> │ 验证密码 → 签发 JWT
  │  {token, user}          │
  │ <────────────────────── │
  │                         │
  │  POST /posts/           │
  │  Authorization: Bearer  │
  │ ──────────────────────> │ 解码 JWT → 查询用户 → current_user
  │  PostResponse           │
  │ <────────────────────── │
```

---

## 🖼 图片上传流程

1. 前端通过 `<input type="file" multiple>` 选择图片
2. 封装为 `FormData`（title + content + files），`POST /posts/`
3. 后端 `_save_image()` 处理每个文件：
   - 生成 `uuid4().hex + 原扩展名` 作为唯一文件名
   - 写入 `app/uploads/` 目录
   - 写入 `post_images` 表（filename + url）
4. 前端通过 `http://127.0.0.1:8000/static/uploads/{filename}` 访问

```
POST /posts/ (FormData)
  │
  ├─ title, content ──────────> posts 表
  │
  └─ files[] ──> _save_image() ──> app/uploads/<uuid>.png  (磁盘)
               │
               └──────────────> post_images 表              (元数据)
```

---

## 🎨 前端设计

- **视图切换**：单页管理，无 Vue Router，通过 `currentView` 状态切换页面
- **状态管理**：`localStorage` 持久化 session（token + user），无 Pinia
- **样式体系**：CSS 变量驱动，Indigo 主色调，白色卡片 + 浅灰背景
- **断点**：移动端适配 `@media (max-width: 768px)`

---

## 📦 部署

```bash
# 后端（生产）
cd fastapi_blog
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 前端（构建）
cd frontent
npm run build      # 输出到 dist/
npm run preview    # 预览构建结果
```

生产环境建议：
- 使用 Nginx 反向代理，静态文件直接由 Nginx 提供
- `echo= False` 关闭 SQL 日志（编辑 `database.py`）
- 通过环境变量设置 `DATABASE_URL` 和 `SECRET_KEY`
- 启用 HTTPS

---

## 📝 License

MIT
