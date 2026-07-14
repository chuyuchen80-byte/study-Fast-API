/**
 * =============================================================================
 *  api/auth.js —— 认证相关 API（登录、注册、获取当前用户、刷新 token）
 * =============================================================================
 *
 * Django 对比：
 *   Django 前端的认证 API 通常集中在一个模块里
 *   这里把 /user/ 路径下与认证相关的调用封装为简洁的函数
 */

import { request } from './client'

/**
 * 用户登录
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{access_token, refresh_token, token_type, user, message}>}
 */
export function login(username, password) {
  return request('/user/login', {
    method: 'POST',
    payload: { username, password },
    skipAuth: true,  // 登录时不需要 token
  })
}

/**
 * 用户注册
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{message, user}>}
 */
export function register(username, password) {
  return request('/user/register', {
    method: 'POST',
    payload: { username, password },
    skipAuth: true,
  })
}

/**
 * 获取当前登录用户信息（用于验证 token 有效性）
 * @returns {Promise<UserResponse>}
 */
export function getMe() {
  return request('/user/me', { method: 'GET' })
}

/**
 * 刷新访问令牌（用 refresh_token 换新的 access_token）
 * @param {string} refreshToken
 * @returns {Promise<{access_token, refresh_token, token_type, user}>}
 */
export function refreshAccessToken(refreshToken) {
  return request('/user/refresh', {
    method: 'POST',
    payload: { refresh_token: refreshToken },
    skipAuth: true,
  })
}

/**
 * 更新用户资料
 * @param {object} data - { username?, bio? }
 * @returns {Promise<UserResponse>}
 */
export function updateProfile(data) {
  return request('/user/me', {
    method: 'PUT',
    payload: data,
  })
}

/**
 * 修改密码
 * @param {string} oldPassword
 * @param {string} newPassword
 * @returns {Promise<{message}>}
 */
export function changePassword(oldPassword, newPassword) {
  return request('/user/me/password', {
    method: 'PUT',
    payload: { old_password: oldPassword, new_password: newPassword },
  })
}

/**
 * 上传用户头像
 * @param {File} file - 图片文件
 * @returns {Promise<UserResponse>}
 */
export function uploadAvatar(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/user/me/avatar', {
    method: 'POST',
    payload: formData,
    isFormData: true,
  })
}

/**
 * 获取用户公开资料
 * @param {number} userId
 * @returns {Promise<{user, posts, total}>}
 */
export function getUserProfile(userId) {
  return request(`/user/${userId}`, { method: 'GET' })
}

/**
 * 退出登录（将当前 token 加入黑名单）
 * @returns {Promise<{message}>}
 */
export function logoutApi() {
  return request('/user/logout', { method: 'POST' })
}