/**
 * =============================================================================
 *  utils/helpers.js —— 公共工具函数
 * =============================================================================
 *
 * Django 对比：
 *   Django 模板中的 template filters（如 {{ date|date:"Y-m-d" }}）
 *   这里在前端 JS 中实现等效功能
 */

/**
 * 格式化日期为中文相对时间
 * 如："刚刚"、"5 分钟前"、"3 小时前"、"2025/01/15"
 *
 * @param {string|Date} dateStr - ISO 日期字符串或 Date 对象
 * @returns {string} 格式化后的时间文本
 */
export function formatDate(dateStr) {
  if (!dateStr) return ''
  // 修复时区：后端存 UTC，JSON 可能不带 Z 后缀 → JS 误当本地时间（CST=UTC+8）
  // 例如 "2026-07-14T09:50:12" → new Date() 按本地时间解析 → 差 8 小时
  // 补上 Z 后缀告诉 JS 这是 UTC 时间 → 正确解析
  let normalized = dateStr
  if (typeof dateStr === 'string' && !/[+-]\d{2}:\d{2}$/.test(dateStr) && !dateStr.endsWith('Z')) {
    normalized = dateStr + 'Z'
  }
  const d = new Date(normalized)
  const now = new Date()
  const diff = now - d

  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 30 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / (24 * 3600000))} 天前`
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/**
 * 截断文本，超出长度用省略号
 *
 * @param {string} text - 原始文本
 * @param {number} maxLen - 最大字符数
 * @returns {string}
 */
export function truncate(text, maxLen = 120) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

/**
 * 获取图片完整 URL（拼接 API base URL 前缀）
 *
 * @param {string} imageUrl - 后端返回的相对路径，如 /static/uploads/xxx.png
 * @returns {string} 完整 URL
 */
export function getImageUrl(imageUrl) {
  if (!imageUrl) return ''
  const base = import.meta.env.VITE_API_BASE_URL || ''
  return `${base}${imageUrl}`
}

/**
 * 获取数字的简短显示（如 1200 → "1.2k"）
 *
 * @param {number} num
 * @returns {string}
 */
export function formatCount(num) {
  if (num >= 10000) return `${(num / 10000).toFixed(1)}w`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
  return String(num)
}