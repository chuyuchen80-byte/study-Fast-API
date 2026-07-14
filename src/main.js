/**
 * =============================================================================
 *  main.js —— Vue 应用入口（Django 的 manage.py + wsgi.py 对应物）
 * =============================================================================
 *
 * Django 对比：
 *   Django 项目:
 *     manage.py runserver  → 启动开发服务器
 *     wsgi.py / asgi.py   → 创建应用实例
 *     settings.py         → 注册 INSTALLED_APPS（路由、中间件等）
 *
 *   Vue 项目:
 *     npm run dev          → 启动 Vite 开发服务器
 *     main.js             → 创建 Vue 应用实例 + 注册插件
 *     createApp(App)
 *       .use(router)      → 注册路由（≈ Django 的 urlpatterns）
 *       .use(pinia)       → 注册状态管理（≈ Django 的 session + cache）
 *       .mount('#app')    → 挂载到 DOM（≈ 渲染到浏览器）
 *
 * v2.0 变化：
 *   旧版只注册了 Vue 本身
 *   新版注册了 Pinia（状态管理）+ Vue Router（前端路由）
 */

import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

const app = createApp(App)

// ── 注册插件 ─────────────────────────────────────────────
// Pinia：必须优先于 router 注册，因为 router 守卫用到了 auth store
app.use(createPinia())
// Vue Router：前端路由管理
app.use(router)

app.mount('#app')