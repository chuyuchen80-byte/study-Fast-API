<script setup>
/**
 * =============================================================================
 *  Navbar.vue —— 顶部导航栏（v2.0 重构版）
 * =============================================================================
 *
 * Django 对比：
 *   Django 的 base.html 模板中包含导航栏 HTML 片段
 *   这里提取为独立的 Vue 组件，使用 Pinia store 代替模板变量
 *
 * 功能：
 *   1. 导航链接（首页 / 论坛 / 发帖） + 路由激活高亮
 *   2. 用户下拉菜单（个人中心 / 设置 / 管理员面板 / 退出）
 *   3. 通知铃铛 + 未读徽章（60 秒轮询）
 *   4. 移动端汉堡菜单响应式展开
 *   5. guest 路由页面不显示导航栏（由 App.vue 的 v-if 控制）
 *
 * 状态来源：
 *   - useAuthStore:    用户信息、登录状态、退出登录
 *   - useNotificationStore: 未读通知数、轮询控制
 */

import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notifications'
import { getImageUrl } from '@/utils/helpers'

// ── 全局依赖 ──────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const notifications = useNotificationStore()

// ── 移动端菜单 ────────────────────────────────────────────

/** 移动端汉堡菜单是否展开 */
const menuOpen = ref(false)

/** 用户下拉菜单是否展开 */
const userMenuOpen = ref(false)

/**
 * 切换移动端菜单
 * 展开时同时关闭用户菜单，反之亦然（防止两个菜单重叠显示）
 */
function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) userMenuOpen.value = false
}

/** 点击导航链接后关闭移动端菜单 */
function closeMenu() {
  menuOpen.value = false
}

/** 切换用户下拉菜单 */
function toggleUserMenu() {
  userMenuOpen.value = !userMenuOpen.value
}

/** 点击外部或菜单项后关闭用户菜单 */
function closeUserMenu() {
  userMenuOpen.value = false
}

// ── 退出登录 ──────────────────────────────────────────────

/**
 * 退出登录：清除 store -> 关闭菜单 -> 跳转首页
 * 停止通知轮询避免未登录状态下的 401 错误
 */
function handleLogout() {
  closeUserMenu()
  closeMenu()
  auth.logout()
  notifications.stopPolling()
  router.push({ name: 'home' })
}

// ── 导航辅助 ──────────────────────────────────────────────

/** 跳转到创建帖子页（需要 auth，router 的 beforeEach 会守卫） */
function goCreate() {
  closeMenu()
  router.push({ name: 'create-post' })
}

/** 判断当前路由是否高亮（用于匹配嵌套路由） */
function isActiveLink(nameOrNames) {
  const names = Array.isArray(nameOrNames) ? nameOrNames : [nameOrNames]
  return names.includes(route.name)
}

// ── 生命周期 ──────────────────────────────────────────────

onMounted(() => {
  // 只有登录用户才轮询通知，非登录用户轮询会报 401
  if (auth.isLoggedIn) {
    notifications.startPolling()
  }
})

onUnmounted(() => {
  notifications.stopPolling()
})
</script>

<template>
  <nav class="app-navbar">
    <!-- ── 左侧：品牌 + 导航链接 ────────────────────────── -->
    <div class="nav-left">
      <!-- 品牌名，点击回首页 -->
      <router-link to="/" class="nav-brand" @click="closeMenu">
        FastAPI Blog
      </router-link>

      <!-- 桌面端导航链接 -->
      <div class="nav-links nav-links-desktop">
        <router-link
          to="/"
          class="nav-link"
          :class="{ active: isActiveLink('home') }"
        >
          首页
        </router-link>
        <router-link
          to="/forum"
          class="nav-link"
          :class="{ active: isActiveLink(['forum', 'post-detail']) }"
        >
          论坛
        </router-link>
        <button
          v-if="auth.isLoggedIn"
          class="nav-link"
          :class="{ active: isActiveLink(['create-post', 'edit-post']) }"
          @click="goCreate"
        >
          + 发帖
        </button>
      </div>
    </div>

    <!-- ── 右侧：通知 + 用户菜单 ──────────────────────────── -->
    <div class="nav-right">
      <!-- ── 通知铃铛 ──────────────────────────────────── -->
      <router-link
        v-if="auth.isLoggedIn"
        to="/notifications"
        class="nav-bell"
        :class="{ active: isActiveLink('notifications') }"
        title="通知"
        @click="closeMenu"
      >
        <span class="bell-icon">&#x1F514;</span>
        <!-- 未读数目徽章 -->
        <span
          v-if="notifications.unreadCount > 0"
          class="bell-badge"
        >
          {{ notifications.unreadCount > 99 ? '99+' : notifications.unreadCount }}
        </span>
      </router-link>

      <!-- ── 未登录：登录/注册按钮 ──────────────────────── -->
      <div v-if="!auth.isLoggedIn" class="nav-user">
        <router-link
          to="/login"
          class="ghost-button"
          :class="{ active: isActiveLink('login') }"
          @click="closeMenu"
        >
          登录
        </router-link>
        <router-link
          to="/register"
          class="ghost-button"
          :class="{ active: isActiveLink('register') }"
          @click="closeMenu"
        >
          注册
        </router-link>
      </div>

      <!-- ── 已登录：用户下拉菜单 ──────────────────────── -->
      <div v-else class="nav-user">
        <div class="user-dropdown-wrapper">
          <button
            class="user-trigger"
            @click.stop="toggleUserMenu"
          >
            <span class="user-avatar">
              <img
                v-if="auth.user?.avatar_url"
                :src="getImageUrl(auth.user.avatar_url)"
                :alt="auth.user?.username"
                class="avatar-img"
              />
              <span v-else class="avatar-letter">
                {{ (auth.user?.username || 'U')[0].toUpperCase() }}
              </span>
            </span>
            <span class="user-name">{{ auth.user?.username }}</span>
            <span class="dropdown-arrow" :class="{ open: userMenuOpen }">▾</span>
          </button>

          <!-- 下拉菜单面板 -->
          <div
            v-if="userMenuOpen"
            class="user-dropdown"
            @click.stop
          >
            <router-link
              v-if="auth.user"
              :to="{ name: 'user-profile', params: { id: auth.user.id } }"
              class="dropdown-item"
              @click="closeUserMenu"
            >
              个人主页
            </router-link>
            <router-link
              to="/favorites"
              class="dropdown-item"
              @click="closeUserMenu"
            >
              我的收藏
            </router-link>
            <router-link
              to="/settings"
              class="dropdown-item"
              @click="closeUserMenu"
            >
              设置
            </router-link>
            <div class="dropdown-divider" />
            <button
              class="dropdown-item dropdown-item-logout"
              @click="handleLogout"
            >
              退出登录
            </button>
          </div>
        </div>
      </div>

      <!-- ── 移动端汉堡按钮 ────────────────────────────── -->
      <button
        class="hamburger"
        :class="{ open: menuOpen }"
        @click="toggleMenu"
        aria-label="切换菜单"
      >
        <span class="hamburger-line" />
        <span class="hamburger-line" />
        <span class="hamburger-line" />
      </button>
    </div>

    <!-- ── 移动端展开菜单 ──────────────────────────────── -->
    <div v-if="menuOpen" class="mobile-menu" @click.stop>
      <router-link
        to="/"
        class="mobile-link"
        :class="{ active: isActiveLink('home') }"
        @click="closeMenu"
      >
        首页
      </router-link>
      <router-link
        to="/forum"
        class="mobile-link"
        :class="{ active: isActiveLink(['forum', 'post-detail']) }"
        @click="closeMenu"
      >
        论坛
      </router-link>
      <button
        v-if="auth.isLoggedIn"
        class="mobile-link mobile-link-btn"
        :class="{ active: isActiveLink(['create-post', 'edit-post']) }"
        @click="goCreate"
      >
        + 发帖
      </button>

      <!-- 移动端分隔线 -->
      <div class="mobile-divider" />

      <template v-if="auth.isLoggedIn">
        <router-link
          to="/notifications"
          class="mobile-link"
          :class="{ active: isActiveLink('notifications') }"
          @click="closeMenu"
        >
          通知
          <span v-if="notifications.unreadCount > 0" class="mobile-badge">
            {{ notifications.unreadCount > 99 ? '99+' : notifications.unreadCount }}
          </span>
        </router-link>
        <router-link
          v-if="auth.user"
          :to="{ name: 'user-profile', params: { id: auth.user.id } }"
          class="mobile-link"
          @click="closeMenu"
        >
          个人主页
        </router-link>
        <router-link
          to="/favorites"
          class="mobile-link"
          @click="closeMenu"
        >
          我的收藏
        </router-link>
        <router-link
          to="/settings"
          class="mobile-link"
          @click="closeMenu"
        >
          设置
        </router-link>
                <button class="mobile-link mobile-link-logout" @click="handleLogout">
          退出登录
        </button>
      </template>
      <template v-else>
        <router-link
          to="/login"
          class="mobile-link"
          :class="{ active: isActiveLink('login') }"
          @click="closeMenu"
        >
          登录
        </router-link>
        <router-link
          to="/register"
          class="mobile-link"
          :class="{ active: isActiveLink('register') }"
          @click="closeMenu"
        >
          注册
        </router-link>
      </template>
    </div>

    <!-- ── 点击遮罩关闭用户菜单 ────────────────────────── -->
    <div
      v-if="userMenuOpen"
      class="menu-overlay"
      @click="closeUserMenu"
    />
  </nav>
</template>

<style scoped>
/* ── 导航栏主体（使用 main.css 的 .app-navbar 类名） ──── */

.app-navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  padding: 16px 32px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  position: relative;
  z-index: 100;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

/* ── 品牌 ────────────────────────────────────────────────── */

.nav-brand {
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--color-text);
  text-decoration: none;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

/* ── 桌面端导航链接 ──────────────────────────────────────── */

.nav-links-desktop {
  display: flex;
  gap: 4px;
}

.nav-link {
  border: 0;
  background: transparent;
  padding: 8px 16px;
  border-radius: 8px;
  color: var(--color-text-secondary);
  font-weight: 500;
  font-size: 0.9rem;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
}

.nav-link:hover {
  background: #f3f4f6;
  color: var(--color-text);
}

.nav-link.active,
.nav-link.router-link-active {
  background: #f3f4f6;
  color: var(--color-text);
}

/* ── 右侧区域 ────────────────────────────────────────────── */

.nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ── 通知铃铛 ────────────────────────────────────────────── */

.nav-bell {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  text-decoration: none;
  transition: background 0.15s ease;
}

.nav-bell:hover,
.nav-bell.active {
  background: #f3f4f6;
}

.bell-icon {
  font-size: 1.15rem;
}

.bell-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--color-danger);
  color: #fff;
  font-size: 0.65rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* ── 未登录按钮 ──────────────────────────────────────────── */

.nav-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ghost-button {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 6px 14px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ghost-button:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

/* ── 用户下拉菜单 ────────────────────────────────────────── */

.user-dropdown-wrapper {
  position: relative;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 6px 10px 6px 6px;
  background: transparent;
  color: var(--color-text);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.user-trigger:hover {
  border-color: var(--color-accent);
}

.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  font-weight: 600;
  font-size: 0.78rem;
  user-select: none;
  overflow: hidden;
}

.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.avatar-letter {
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
}

.user-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-arrow {
  font-size: 0.7rem;
  color: var(--color-text-secondary);
  transition: transform 0.2s ease;
}

.dropdown-arrow.open {
  transform: rotate(180deg);
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 160px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  box-shadow: var(--shadow-md);
  padding: 6px;
  z-index: 200;
  display: grid;
}

.dropdown-item {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 9px 14px;
  border-radius: 7px;
  color: var(--color-text);
  font-size: 0.88rem;
  text-decoration: none;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s ease;
}

.dropdown-item:hover {
  background: #f3f4f6;
}

.dropdown-item-admin {
  color: var(--color-accent);
  font-weight: 500;
}

.dropdown-item-logout {
  color: var(--color-danger);
  font-weight: 500;
}

.dropdown-item-logout:hover {
  background: #fef2f2;
}

.dropdown-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 8px;
}

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 150;
  /* transparent overlay catches clicks outside dropdown */
}

/* ── 移动端汉堡按钮 ──────────────────────────────────────── */

.hamburger {
  display: none;
  flex-direction: column;
  gap: 5px;
  border: 0;
  background: transparent;
  padding: 6px;
  cursor: pointer;
}

.hamburger-line {
  display: block;
  width: 22px;
  height: 2px;
  background: var(--color-text);
  border-radius: 1px;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

/* 汉堡按钮打开动画：中间线消失，上下线旋转形成 X */
.hamburger.open .hamburger-line:nth-child(1) {
  transform: translateY(7px) rotate(45deg);
}

.hamburger.open .hamburger-line:nth-child(2) {
  opacity: 0;
}

.hamburger.open .hamburger-line:nth-child(3) {
  transform: translateY(-7px) rotate(-45deg);
}

/* ── 移动端展开菜单 ──────────────────────────────────────── */

.mobile-menu {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-md);
  padding: 12px 24px;
  z-index: 150;
  flex-direction: column;
  gap: 4px;
}

.mobile-link {
  display: block;
  padding: 10px 14px;
  border-radius: 8px;
  color: var(--color-text);
  font-size: 0.95rem;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.1s ease;
}

.mobile-link:hover,
.mobile-link.active {
  background: #f3f4f6;
}

.mobile-link-btn {
  border: 0;
  background: transparent;
  width: 100%;
  text-align: left;
  cursor: pointer;
  color: var(--color-accent);
  font-weight: 600;
}

.mobile-link-admin {
  color: var(--color-accent);
}

.mobile-link-logout {
  border: 0;
  background: transparent;
  width: 100%;
  text-align: left;
  cursor: pointer;
  color: var(--color-danger);
  font-weight: 500;
}

.mobile-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 8px;
}

.mobile-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--color-danger);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  margin-left: 8px;
  vertical-align: middle;
}

/* ── 响应式断点 ──────────────────────────────────────────── */

@media (max-width: 768px) {
  .app-navbar {
    padding: 12px 18px;
    flex-wrap: wrap;
  }

  .nav-links-desktop {
    display: none;
  }

  .nav-right {
    gap: 6px;
  }

  /* 移动端隐藏用户名，只显示头像 */
  .user-name {
    display: none;
  }

  .hamburger {
    display: flex;
  }

  .mobile-menu {
    display: flex;
  }
}

/* ── 更小屏幕（~480px）额外调整 ─────────────────────────── */

@media (max-width: 480px) {
  .ghost-button {
    padding: 4px 10px;
    font-size: 0.8rem;
  }

  .nav-user {
    gap: 6px;
  }
}
</style>