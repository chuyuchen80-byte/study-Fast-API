/**
 * =============================================================================
 *  api/notifications.js —— 通知相关 API
 * =============================================================================
 */

import { request } from './client'

/**
 * 获取通知列表
 * @param {object} options
 * @param {number} options.page - 页码
 * @param {number} options.page_size - 每页条数
 * @param {boolean} options.unread_only - 只看未读
 * @returns {Promise<{notifications, total, unread_count, page, page_size}>}
 */
export function getNotifications({ page = 1, page_size = 50, unread_only = false } = {}) {
  const query = new URLSearchParams({ page, page_size })
  if (unread_only) query.append('unread_only', 'true')
  return request(`/notifications/?${query.toString()}`)
}

/**
 * 获取未读通知数量（用于导航栏小红点）
 * @returns {Promise<{unread_count}>}
 */
export function getUnreadCount() {
  return request('/notifications/unread-count')
}

/**
 * 标记单条通知为已读
 * @param {number} notificationId
 * @returns {Promise<{message}>}
 */
export function markAsRead(notificationId) {
  return request(`/notifications/${notificationId}/read`, { method: 'PUT' })
}

/**
 * 标记所有通知为已读
 * @returns {Promise<{message}>}
 */
export function markAllAsRead() {
  return request('/notifications/read-all', { method: 'PUT' })
}