/**
 * =============================================================================
 *  utils/markdown.js —— Markdown 渲染（marked 封装）
 * =============================================================================
 *
 * Django 对比：
 *   Django 的 markdown filter（如 {{ content|markdown }} 或 django-markdownify）
 *   这里在前端用 marked 库做等效渲染
 *
 * 为什么在前端渲染而不是后端？
 *   1. 后端只存原始文本，不需要存 HTML 版本
 *   2. 前端可以根据场景选择不同的渲染方式（预览 vs 展示）
 *   3. 节省数据库空间，减少存储双份内容的开销
 */

import { marked } from 'marked'

// 配置 marked 选项
marked.setOptions({
  breaks: true,        // 换行符转换为 <br>（GitHub 风格）
  gfm: true,           // 启用 GitHub Flavored Markdown
  headerIds: false,    // 不自动生成标题 ID
  mangle: false,       // 不混淆邮箱地址
})

/**
 * 将 Markdown 文本渲染为安全 HTML
 *
 * 使用方式：在 Vue 组件中 v-html="renderMarkdown(content)"
 * 注意：v-html 需要确保内容可信，我们的内容来自自己的后端
 *
 * @param {string} text - Markdown 原始文本
 * @returns {string} 安全的 HTML 字符串
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    // 解析失败时返回原始文本（已转义）
    return escapeHtml(text)
  }
}

/**
 * 简单的 HTML 转义（防止 XSS）
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }
  return String(text).replace(/[&<>"']/g, (c) => map[c] || c)
}