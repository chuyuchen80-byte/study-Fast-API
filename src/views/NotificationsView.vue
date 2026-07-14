<script setup>
/**
 * =============================================================================
 *  NotificationsView.vue —— 通知列表页面
 * =============================================================================
 *
 * Django 对比：类似 django-notifications-hq 的通知列表视图
 *   后端 Django 中，通知通常存储在 Notification 模型中，
 *   用户访问 /notifications/ 页面时查询当前用户的所有通知并分页展示。
 *   这里前端调用 getNotifications API 获取分页列表。
 *
 * 路由：/notifications → name: 'notifications'（requiresAuth: true）
 *   未登录用户会被全局路由守卫重定向到登录页。
 *
 * 功能：
 *   1. 分页通知列表（默认每页 50 条）
 *   2. 未读通知高亮显示（左侧蓝色边框 + 淡蓝背景 + 蓝点指示器）
 *   3. 通知类型图标：like=❤️, comment=💬, reply=↩️, system=📢
 *   4. 点击单条通知 → 标记已读 + 跳转相关帖子
 *   5. "全部标为已读" 按钮（一键清除所有未读状态）
 *   6. 头部显示未读数徽章
 *   7. 更新全局通知 store 的未读计数
 *   8. 加载/空状态覆盖
 */
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'
import * as notificationsApi from '@/api/notifications'
import { formatDate } from '@/utils/helpers'
import Pagination from '@/components/Pagination.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const notifStore = useNotificationStore()

// ── 状态 ──────────────────────────────────────────────────────

/** 通知列表 */
const notifications = ref([])

/** 通知总数 */
const total = ref(0)

/** 未读数量 */
const unreadCount = ref(0)

/** 当前页码 */
const page = ref(1)

/** 每页条数 */
const pageSize = 50

/** 是否正在加载 */
const isLoading = ref(true)

/** 全局「全部已读」操作进行中 */
const markingAll = ref(false)

// ── 计算属性 ──────────────────────────────────────────────────

/** 总页数 */
const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)

/** 是否有未读通知 */
const hasUnread = computed(() => unreadCount.value > 0)

// ── 通知类型 → 图标映射 ──────────────────────────────────────

/** 根据通知 type 字段返回对应 emoji 图标 */
const typeIcons = {
  like: '❤️',
  comment: '💬',
  reply: '↩️',
  follow: '👤',
  system: '📢',
}

// ── API 数据加载 ──────────────────────────────────────────────

/**
 * 获取通知列表
 * 请求参数：page, page_size（固定 50）
 * 响应：{ notifications, total, unread_count, page, page_size }
 */
async function fetchNotifications() {
  isLoading.value = true
  try {
    const data = await notificationsApi.getNotifications({
      page: page.value,
      page_size: pageSize,
    })
    notifications.value = data.notifications || []
    total.value = data.total || 0
    unreadCount.value = data.unread_count || 0
  } catch {
    // 网络错误或未登录，静默处理
  } finally {
    isLoading.value = false
  }
}

// ── 交互事件 ──────────────────────────────────────────────────

/**
 * 点击通知项
 * 1. 未读 → 调用 markAsRead API 标记已读 + 更新 store
 * 2. 有 related_post_id → 跳转到对应帖子详情页
 */
async function handleClick(notif) {
  if (!notif.is_read) {
    try {
      await notificationsApi.markAsRead(notif.id)
      // 乐观更新本地状态
      notif.is_read = true
      notifStore.decrement(1)
    } catch {
      // 标记失败不影响导航，静默处理
    }
  }
  // 跳转到关联帖子
  if (notif.related_post_id) {
    router.push({ name: 'post-detail', params: { id: notif.related_post_id } })
  }
}

/**
 * 一键标记所有通知为已读
 * 调用 markAllAsRead API → 更新本地列表所有项状态 → 清除 store 未读数
 */
async function handleMarkAllRead() {
  if (markingAll.value) return
  markingAll.value = true
  try {
    await notificationsApi.markAllAsRead()
    // 本地全部标记
    notifications.value.forEach((n) => {
      n.is_read = true
    })
    notifStore.clearAll()
  } catch {
    // 静默处理
  } finally {
    markingAll.value = false
  }
}

/**
 * 翻页
 */
function goToPage(p) {
  page.value = p
  fetchNotifications()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(fetchNotifications)
</script>

<template>
  <section class="forum-container">
    <!-- ── 页面 Header ─────────────────────────────────────── -->
    <div class="forum-header">
      <h2>
        通知
        <span v-if="unreadCount" class="unread-badge">{{ unreadCount }}</span>
      </h2>
      <button
        v-if="hasUnread"
        class="btn-secondary"
        :disabled="markingAll"
        @click="handleMarkAllRead"
      >
        {{ markingAll ? '处理中...' : '全部标为已读' }}
      </button>
    </div>

    <!-- ── 加载状态 ──────────────────────────────────────── -->
    <LoadingSpinner v-if="isLoading" message="加载通知..." />

    <!-- ── 空状态 ────────────────────────────────────────── -->
    <div v-else-if="notifications.length === 0" class="empty-state">
      <p>暂无通知</p>
    </div>

    <!-- ── 通知列表 ──────────────────────────────────────── -->
    <div v-else class="notification-list">
      <div
        v-for="notif in notifications"
        :key="notif.id"
        class="notification-item"
        :class="{ unread: !notif.is_read }"
        @click="handleClick(notif)"
      >
        <!-- 类型图标 -->
        <span class="notif-icon">{{ typeIcons[notif.type] || '📌' }}</span>

        <!-- 消息正文 -->
        <div class="notif-body">
          <p class="notif-message">{{ notif.message }}</p>
          <span class="notif-time">{{ formatDate(notif.created_at) }}</span>
        </div>

        <!-- 未读指示点 -->
        <span v-if="!notif.is_read" class="unread-dot" />
      </div>
    </div>

    <!-- ── 分页 ──────────────────────────────────────────── -->
    <Pagination
      v-if="total > pageSize"
      :page="page"
      :total-pages="totalPages"
      @change="goToPage"
    />
  </section>
</template>

<style scoped>
/* ── 通知列表 ──────────────────────────────────────────────── */

.notification-list {
  display: grid;
  gap: 2px;
}

.notification-item {
  display: flex;
  gap: 14px;
  padding: 16px 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  cursor: pointer;
  align-items: flex-start;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}

.notification-item:hover {
  background: #f9fafb;
  box-shadow: var(--shadow);
}

/* 未读通知特殊样式：左侧蓝色强调线 + 淡蓝背景 */
.notification-item.unread {
  border-left: 3px solid var(--color-accent);
  background: #eef2ff;
}

.notif-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
  line-height: 1.4;
  padding-top: 1px;
}

.notif-body {
  flex: 1;
  min-width: 0;
}

.notif-message {
  margin: 0 0 4px;
  font-size: 0.93rem;
  color: var(--color-text);
  line-height: 1.5;
  word-break: break-word;
}

.notif-time {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

/* 未读蓝点指示器 */
.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
  margin-top: 6px;
}

/* 头部未读数量徽章（红色圆角标签） */
.unread-badge {
  display: inline-flex;
  align-items: center;
  background: var(--color-danger);
  color: #fff;
  padding: 1px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 8px;
  line-height: 1.4;
}

/* ── 空状态 ────────────────────────────────────────────────── */

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--color-text-secondary);
}

.empty-state p {
  font-size: 0.95rem;
  margin: 0;
}

/* ── 响应式 ────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .forum-header {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }

  .notification-item {
    padding: 14px 16px;
  }
}
</style>