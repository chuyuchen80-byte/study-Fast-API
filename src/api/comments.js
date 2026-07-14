/**
 * =============================================================================
 *  api/comments.js —— 评论相关 API
 * =============================================================================
 */

import { request } from './client'

/**
 * 获取帖子的评论列表（含嵌套回复）
 * @param {number} postId
 * @returns {Promise<CommentResponse[]>}
 */
export function getComments(postId) {
  return request(`/posts/${postId}/comments`)
}

/**
 * 添加评论（或回复评论）
 * @param {number} postId
 * @param {string} content - 评论内容
 * @param {number|null} parentId - 回复某条评论时传入该评论 ID，顶级评论传 null
 * @returns {Promise<CommentResponse>}
 */
export function addComment(postId, content, parentId = null) {
  return request(`/posts/${postId}/comments`, {
    method: 'POST',
    payload: { content, parent_id: parentId },
  })
}

/**
 * 编辑评论（仅限作者本人）
 * @param {number} postId
 * @param {number} commentId
 * @param {string} content - 修改后的内容
 * @returns {Promise<CommentResponse>}
 */
export function updateComment(postId, commentId, content) {
  return request(`/posts/${postId}/comments/${commentId}`, {
    method: 'PUT',
    payload: { content },
  })
}

/**
 * 删除评论（作者或管理员）
 * @param {number} postId
 * @param {number} commentId
 * @returns {Promise<null>}
 */
export function deleteComment(postId, commentId) {
  return request(`/posts/${postId}/comments/${commentId}`, { method: 'DELETE' })
}