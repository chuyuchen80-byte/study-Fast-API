/**
 * =============================================================================
 *  router/index.js —— Vue Router 路由配置（Django 的 urls.py 对应物）
 * =============================================================================
 *
 * Django 对比：
 *   Django 的 URL 路由在后端（urls.py），Vue Router 在前端做类似的事
 *   两者都是"路径 → 组件"的映射
 *
 *   后端路由 vs 前端路由：
 *     后端路由：每次 URL 变化都向服务器发请求，服务器返回新页面
 *     前端路由：URL 变化由 JS 拦截，切换组件但不刷新页面（SPA 单页应用）
 *
 * 路由守卫：
 *   beforeEach 钩子在每次路由切换前执行，检查登录状态
 *   类似 Django 的 LoginRequiredMixin 或 @login_required
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/AuthView.vue'),
    props: { defaultTab: 'login' },
    meta: { guest: true },  // 已登录用户访问此页 → 重定向到首页
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/AuthView.vue'),
    props: { defaultTab: 'register' },
    meta: { guest: true },
  },
  {
    path: '/forum',
    name: 'forum',
    component: () => import('@/views/ForumView.vue'),
  },
  {
    path: '/post/:id',
    name: 'post-detail',
    component: () => import('@/views/PostDetailView.vue'),
    props: true,  // 将路由参数作为 props 传给组件
  },
  {
    path: '/create',
    name: 'create-post',
    component: () => import('@/views/CreatePostView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/edit/:id',
    name: 'edit-post',
    component: () => import('@/views/CreatePostView.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id',
    name: 'user-profile',
    component: () => import('@/views/UserProfileView.vue'),
    props: true,
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/FavoritesView.vue'),
    meta: { requiresAuth: true },
  },
  {
    // 404 捕获所有未匹配路由
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),  // 使用 HTML5 History API（无 # 的干净 URL）
  routes,
  scrollBehavior() {
    return { top: 0 }  // 每次路由切换滚动到顶部
  },
})

// ── 全局路由守卫 ─────────────────────────────────────────
// Django 对比：相当于 Django 中间件 + @login_required 的组合

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    // 需要登录但未登录 → 跳转登录页，登录后跳回来
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.meta.guest && auth.isLoggedIn) {
    // 已登录但访问登录/注册页 → 重定向到首页
    next({ name: 'home' })
  } else {
    next()
  }
})

export default router