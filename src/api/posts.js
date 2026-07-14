/**
 * =============================================================================
 *  api/posts.js —— 帖子相关 API（CRUD + 分类/标签 + 点赞收藏 + 搜索）
 * =============================================================================
 */

import { request, uploadRequest } from './client'

/**
 * 获取帖子列表（支持分页、搜索、分类/标签筛选）
 * @param {object} params
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} params.q - 搜索关键词（可选）
 * @param {number} params.category_id - 分类 ID（可选）
 * @param {string} params.tag - 标签名（可选）
 * @returns {Promise<{posts, total, page, page_size}>}
 */
export function getPosts({ page = 1, page_size = 20, q, category_id, tag } = {}) {
  const query = new URLSearchParams({ page, page_size })
  if (q) query.append('q', q)
  if (category_id) query.append('category_id', category_id)
  if (tag) query.append('tag', tag)
  return request(`/posts/?${query.toString()}`)
}

/**
 * 获取单个帖子详情
 * @param {number} postId
 * @returns {Promise<PostResponse>}
 */
export function getPost(postId) {
  return request(`/posts/${postId}`)
}

/**
 * 创建帖子（支持图片上传）
 * @param {object} data - { title, content, category_id?, tags?, files? }
 * @returns {Promise<PostResponse>}
 */
export function createPost({ title, content, category_id, tags, files = [] }) {
  return uploadRequest(
    '/posts/',
    {
      title,
      content,
      ...(category_id && { category_id }),
      ...(tags && { tags }),
    },
    files,
  )
}

/**
 * 更新帖子
 * @param {number} postId
 * @param {object} data - { title?, content?, category_id?, tags? }
 * @returns {Promise<PostResponse>}
 */
export function updatePost(postId, data) {
  return request(`/posts/${postId}`, { method: 'PUT', payload: data })
}

/**
 * 删除帖子
 * @param {number} postId
 * @returns {Promise<null>}
 */
export function deletePost(postId) {
  return request(`/posts/${postId}`, { method: 'DELETE' })
}

/**
 * 切换帖子点赞状态（已点赞 → 取消，未点赞 → 点赞）
 * @param {number} postId
 * @returns {Promise<{active, count}>}
 */
export function toggleLike(postId) {
  return request(`/posts/${postId}/like`, { method: 'POST' })
}

/**
 * 获取当前用户对该帖子的点赞状态
 * @param {number} postId
 * @returns {Promise<{liked}>}
 */
export function getLikeStatus(postId) {
  return request(`/posts/${postId}/like-status`)
}

/**
 * 切换帖子收藏状态
 * @param {number} postId
 * @returns {Promise<{active, count}>}
 */
export function toggleFavorite(postId) {
  return request(`/posts/${postId}/favorite`, { method: 'POST' })
}

/**
 * 获取当前用户的收藏帖子列表
 * @param {number} page - 页码
 * @param {number} page_size - 每页条数
 * @returns {Promise<{posts, total, page, page_size}>}
 */
export function getFavorites(page = 1, page_size = 20) {
  return request(`/user/me/favorites?page=${page}&page_size=${page_size}`)
}

/**
 * 为帖子追加图片
 * @param {number} postId
 * @param {File[]} files
 * @returns {Promise<PostImageResponse[]>}
 */
export function uploadPostImages(postId, files) {
  return uploadRequest(`/posts/${postId}/images`, {}, files)
}

/**
 * 切换帖子置顶（管理员操作）
 * @param {number} postId
 * @returns {Promise<{is_pinned}>}
 */
export function togglePin(postId) {
  return request(`/posts/${postId}/pin`, { method: 'POST' })
}

/**
 * 切换帖子精华（管理员操作）
 * @param {number} postId
 * @returns {Promise<{is_featured}>}
 */
export function toggleFeature(postId) {
  return request(`/posts/${postId}/feature`, { method: 'POST' })
}