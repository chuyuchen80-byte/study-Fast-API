<script setup>
/**
 * =============================================================================
 *  NotFoundView.vue —— 404 页面未找到
 * =============================================================================
 *
 * Django 对比：Django 的 handler404 自定义 404 页面
 *   后端 Django 中，404 页面由 handler404 视图渲染，通常是一个简单模板。
 *   这里前端 Vue Router 通过 catch-all 路由 :pathMatch(.*)* 捕获所有
 *   未被前面路由匹配的路径，渲染此组件。
 *
 * 路由：/:pathMatch(.*)* → name: 'not-found'
 *   这是路由表中的最后一条（catch-all），匹配所有未定义路径。
 *
 * 功能：
 *   1. 大号 "404" 错误码
 *   2. 友好的错误提示文字
 *   3. "返回首页" 按钮 + "返回上一页" 链接
 */

import { useRouter } from 'vue-router'

const router = useRouter()

/** 跳转到首页 */
function goHome() {
  router.push({ name: 'home' })
}

/** 返回上一页（可用于浏览器历史中还有页面时） */
function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push({ name: 'home' })
  }
}
</script>

<template>
  <section class="not-found-page">
    <div class="not-found-content">
      <!-- 404 大字 -->
      <h1 class="error-code">404</h1>

      <!-- 提示标题 -->
      <h2 class="error-title">页面未找到</h2>

      <!-- 提示文字 -->
      <p class="error-description">
        你访问的页面不存在、已被移除或地址输入有误。
      </p>

      <!-- 操作按钮 -->
      <div class="error-actions">
        <button class="btn-primary" @click="goHome">
          返回首页
        </button>
        <button class="btn-secondary" @click="goBack">
          返回上一页
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ── 页面布局 ──────────────────────────────────────────────── */

.not-found-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
  padding: 40px 20px;
}

.not-found-content {
  text-align: center;
  max-width: 460px;
}

/* ── 404 大字 ───────────────────────────────────────────────── */

.error-code {
  font-size: 6rem;
  font-weight: 800;
  color: var(--color-accent);
  margin: 0;
  line-height: 1;
  letter-spacing: -0.04em;
  opacity: 0.15;
}

/* ── 标题 ──────────────────────────────────────────────────── */

.error-title {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--color-text);
  margin: -12px 0 12px;
  letter-spacing: -0.02em;
}

/* ── 描述文字 ──────────────────────────────────────────────── */

.error-description {
  color: var(--color-text-secondary);
  font-size: 0.95rem;
  margin: 0 0 28px;
  line-height: 1.6;
}

/* ── 操作按钮行 ────────────────────────────────────────────── */

.error-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ── 响应式 ────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .error-code {
    font-size: 4.5rem;
  }

  .error-title {
    font-size: 1.2rem;
  }

  .error-actions {
    flex-direction: column;
    align-items: center;
  }
}
</style>