"""
=============================================================================
 routers/notifications.py —— 通知路由（v2.0 新增文件）
=============================================================================

Django 对比：
   Django: django-notifications 包的 views + urls
   FastAPI: APIRouter 集中管理通知端点

端点一览：
   GET  /notifications                 → 通知列表（分页 + 未读数）
   GET  /notifications/unread-count    → 未读通知计数
   PUT  /notifications/{id}/read       → 标记单条已读
   PUT  /notifications/read-all        → 全部标记已读

通知类型（models.py 中定义）：
   like     → 有人点赞了你的帖子
   comment  → 有人评论了你的帖子
   reply    → 有人回复了你的评论
   system   → 系统通知（如帖子被设为精华）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Notification, User
from app.schemas import NotificationListResponse, NotificationResponse

# Router 定义
router = APIRouter(prefix="/notifications", tags=["通知"])


# =========================================================================
# GET /notifications —— 通知列表（v2.0 新增）
# =========================================================================

@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的通知列表（需登录，分页）。

    v2.0 新增端点。

    返回结构：
      {
        "notifications": [...],   // 当前页通知列表
        "total": 42,              // 全部通知总数
        "unread_count": 5,        // 未读通知数（用于前端红点 badge）
        "page": 1,
        "page_size": 20
      }

    未读数独立于分页查询 —— 用户在第 3 页也能看到"有 5 条未读"。

    Django 对比：
      notifications = request.user.notifications.order_by('-created_at')
      unread_count = request.user.notifications.filter(is_read=False).count()
    """
    # 查询总数
    total_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id
        )
    )
    total = total_result.scalar() or 0

    # 查询未读数
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    unread_count = unread_result.scalar() or 0

    # 查询当前页通知（按时间倒序，最新的在前）
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    notifications = result.scalars().all()

    return NotificationListResponse(
        notifications=[
            NotificationResponse.model_validate(n) for n in notifications
        ],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


# =========================================================================
# GET /notifications/unread-count —— 未读计数（v2.0 新增）
# =========================================================================

@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的未读通知数量（需登录）。

    v2.0 新增端点。

    使用场景：
      前端定时轮询（如每 60 秒）→ 更新导航栏的未读 badge
      比每次都请求完整通知列表高效得多（只传一个数字）

    返回：{ "unread_count": 5 }

    Django 对比：
      Notification.objects.filter(user=request.user, is_read=False).count()
    """
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    count = result.scalar() or 0
    return {"unread_count": count}


# =========================================================================
# PUT /notifications/{notification_id}/read —— 标记单条已读（v2.0 新增）
# =========================================================================

@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    将单条通知标记为已读（需登录）。

    v2.0 新增端点。

    安全限制：只能标记自己的通知（同时检查 notification_id + user_id），
    防止用户通过遍历 ID 标记别人的通知为已读。

    Django 对比：
      notification = get_object_or_404(Notification, id=id, user=request.user)
      notification.is_read = True
      notification.save()
    """
    # 同时限定 id 和 user_id，确保只能操作自己的通知
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")

    notification.is_read = True
    await db.commit()
    await db.refresh(notification)

    return NotificationResponse.model_validate(notification)


# =========================================================================
# PUT /notifications/read-all —— 全部标记已读（v2.0 新增）
# =========================================================================

@router.put("/read-all")
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    将当前用户的所有未读通知标记为已读（需登录）。

    v2.0 新增端点。

    使用场景：用户点击"全部已读"按钮 → 一键清除所有未读红点。

    实现方式：用 SQL UPDATE 批量操作（一条 SQL 更新所有行），
    而不是逐条查询 + 修改 + 提交（N 条记录要 N 次 SQL）。

    Django 对比：
      Notification.objects.filter(user=request.user, is_read=False)
          .update(is_read=True)
      → 同样是单条 SQL 批量更新
    """
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()

    return {"message": "已全部标记为已读"}