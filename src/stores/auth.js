/**
 * =============================================================================
 *  stores/auth.js —— Pinia 认证状态管理（Django 的 session + request.user 对应物）
 * =============================================================================
 *
 * Pinia 是什么？
 *   类似 Vuex 但更简单，是 Vue 3 官方推荐的全局状态管理方案
 *   Store = 把所有组件共享的数据集中到一个地方管理
 *
 * Django 对比：
 *   Django 的 request.user 是框架自动管理的 —— 我们这里手动管理
 *   Pinia store ≈ 把 request.user + login() + logout() 集中在一个模块
 *   localStorage 持久化 ≈ Django 的 SESSION_COOKIE（存在浏览器端）
 *
 * 核心设计：
 *   1. state: user, token, refreshToken —— 全局共享的认证数据
 *   2. getters: isLoggedIn, isAdmin —— 派生计算属性
 *   3. actions: login, register, logout, restoreSession —— 业务操作
 *   4. localStorage 持久化 —— 刷新页面后保持登录状态
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getMe, refreshAccessToken, logoutApi } from '@/api/auth'

const STORAGE_KEY = 'fastapi-blog-session'

export const useAuthStore = defineStore('auth', () => {
  // ── 状态（State） ──────────────────────────────────────

  /** @type {import('vue').Ref<object|null>} 当前登录用户对象 */
  const user = ref(null)

  /** @type {import('vue').Ref<string>} JWT 访问令牌（短有效期） */
  const token = ref('')

  /** @type {import('vue').Ref<string>} JWT 刷新令牌（长有效期） */
  const refreshToken = ref('')

  // ── 计算属性（Getters） ────────────────────────────────

  /** 是否已登录 */
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  /** 是否为管理员 */
  const isAdmin = computed(() => user.value?.is_admin ?? false)

  // ── localStorage 持久化 ───────────────────────────────

  function loadFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      if (saved?.token) {
        user.value = saved.user || null
        token.value = saved.token
        refreshToken.value = saved.refreshToken || ''
      }
      // 移除旧的 legacy key（v1 版本的存储格式）
      localStorage.removeItem('fastapi-blog-user')
    } catch {
      // localStorage 数据损坏，忽略
    }
  }

  function saveToStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      user: user.value,
      token: token.value,
      refreshToken: refreshToken.value,
    }))
  }

  function clearStorage() {
    localStorage.removeItem(STORAGE_KEY)
  }

  // ── 操作（Actions） ────────────────────────────────────

  /**
   * 用户登录 —— 调用 API 获取 token，保存到 store 和 localStorage
   * @param {string} username
   * @param {string} password
   * @returns {Promise<object>} 登录响应
   */
  async function login(username, password) {
    const data = await apiLogin(username, password)
    user.value = data.user
    token.value = data.access_token
    refreshToken.value = data.refresh_token || ''
    saveToStorage()
    return data
  }

  /**
   * 用户注册 —— 调用 API 注册新用户
   * @param {string} username
   * @param {string} password
   * @returns {Promise<object>} 注册响应
   */
  async function register(username, password) {
    return apiRegister(username, password)
  }

  /**
   * 恢复登录状态（应用启动时调用）
   * 验证 token 是否仍然有效，过期则尝试用 refresh_token 续期
   */
  async function restoreSession() {
    if (!token.value) return
    try {
      const userData = await getMe()
      user.value = userData
    } catch {
      // Token 过期，尝试刷新
      if (refreshToken.value) {
        try {
          const refreshData = await refreshAccessToken(refreshToken.value)
          token.value = refreshData.access_token
          refreshToken.value = refreshData.refresh_token || ''
          saveToStorage()

          const userData = await getMe()
          user.value = userData
          return
        } catch {
          // refresh token 也过期了
        }
      }
      logout()
    }
  }

  /**
   * 更新当前用户资料（store 中同步更新）
   * @param {object} userData - 更新后的用户数据
   */
  function updateProfileLocal(userData) {
    user.value = { ...user.value, ...userData }
    saveToStorage()
  }

  /**
   * 退出登录 —— 清除 store 和 localStorage
   * 尝试通知服务端将 token 加入黑名单（不阻塞）
   */
  function logout() {
    // 异步通知服务端（不等待结果）
    if (token.value) {
      logoutApi().catch(() => { /* 忽略网络错误 */ })
    }
    user.value = null
    token.value = ''
    refreshToken.value = ''
    clearStorage()
  }

  // ── 初始化 ─────────────────────────────────────────────
  loadFromStorage()

  return {
    // state
    user,
    token,
    refreshToken,
    // getters
    isLoggedIn,
    isAdmin,
    // actions
    login,
    register,
    logout,
    restoreSession,
    updateProfileLocal,
  }
})