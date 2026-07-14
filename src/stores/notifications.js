/**
 * =============================================================================
 *  stores/notifications.js —— 通知状态管理
 * =============================================================================
 *
 * 管理未读通知计数（用于导航栏小红点）
 * 轮询策略：每 60 秒刷新一次未读数
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUnreadCount } from '@/api/notifications'

export const useNotificationStore = defineStore('notifications', () => {
  const unreadCount = ref(0)
  let pollTimer = null

  /** 获取未读通知数 */
  async function fetchUnreadCount() {
    try {
      const data = await getUnreadCount()
      unreadCount.value = data.unread_count || 0
    } catch {
      // 未登录或网络错误，忽略
    }
  }

  /** 开始轮询（在 Navbar 挂载时调用） */
  function startPolling(intervalMs = 60000) {
    fetchUnreadCount()
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(fetchUnreadCount, intervalMs)
  }

  /** 停止轮询（在 Navbar 卸载时调用） */
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  /** 减少未读数（手动标记已读后调用） */
  function decrement(count = 1) {
    unreadCount.value = Math.max(0, unreadCount.value - count)
  }

  /** 全部已读 */
  function clearAll() {
    unreadCount.value = 0
  }

  return {
    unreadCount,
    fetchUnreadCount,
    startPolling,
    stopPolling,
    decrement,
    clearAll,
  }
})