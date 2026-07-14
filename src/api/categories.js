/**
 * =============================================================================
 *  api/categories.js —— 分类/标签相关 API
 * =============================================================================
 */

import { request } from './client'

/**
 * 获取所有分类列表
 * @returns {Promise<CategoryResponse[]>}
 */
export function getCategories() {
  return request('/categories')
}

/**
 * 创建分类（管理员操作）
 * @param {string} name - 分类名称
 * @param {string} description - 分类描述（可选）
 * @returns {Promise<CategoryResponse>}
 */
export function createCategory(name, description) {
  return request('/categories', {
    method: 'POST',
    payload: { name, description },
  })
}

/**
 * 搜索/获取标签列表
 * @param {string} q - 搜索关键词（可选，返回匹配的标签）
 * @returns {Promise<TagResponse[]>}
 */
export function getTags(q = '') {
  const query = q ? `?q=${encodeURIComponent(q)}` : ''
  return request(`/tags${query}`)
}

/**
 * 创建标签
 * @param {string} name - 标签名称
 * @returns {Promise<TagResponse>}
 */
export function createTag(name) {
  return request('/tags', { method: 'POST', payload: { name } })
}