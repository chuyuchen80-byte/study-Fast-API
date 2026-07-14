<script setup>
/**
 * =============================================================================
 *  App.vue —— 根组件（v2.0 重构版 —— 使用 Vue Router + Pinia）
 * =============================================================================
 *
 * 旧版问题：
 *   所有状态（auth、view切换、表单数据）全塞在 App.vue 里 → 244 行混乱
 *   手动 currentView 字符串切换 → 没有 URL 路由
 *   重复的 request() 函数各自为政
 *
 * 新版设计：
 *   App.vue 只做两件事：
 *     1. 启动时恢复登录状态（restoreSession）
 *     2. 提供 <Navbar> + <RouterView> 布局壳
 *   具体页面逻辑全部在 views/ 下的各个组件中
 *
 * Django 对比：
 *   旧版 ≈ Django 的 function-based view 全部写在一个 views.py 里
 *   新版 ≈ Django 的 class-based view 拆分到不同模块 + URL 路由分发
 */

import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Navbar from '@/components/Navbar.vue'

const auth = useAuthStore()
const route = useRoute()

onMounted(() => {
  // 应用启动：从 localStorage 恢复登录状态
  // 如果 token 过期，restoreSession 会自动尝试刷新或退出
  auth.restoreSession()
})
</script>

<template>
  <div class="page-shell">
    <!--
      导航栏：guest 路由（登录/注册页）不显示导航栏
      Django 对比：base.html 模板里判断 {% if user.is_authenticated %} 显示导航
      key=route.fullPath 确保路由切换时 Navbar 正确响应
    -->
    <Navbar v-if="!route.meta.guest" :key="route.fullPath" />

    <!--
      RouterView：当前路由匹配到的组件在这里渲染
      Django 对比：{% block content %}{% endblock %}
      keep-alive 可选：缓存组件状态，切换回来不丢失
    -->
    <RouterView />
  </div>
</template>