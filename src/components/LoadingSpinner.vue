<script setup>
/**
 * =============================================================================
 *  LoadingSpinner.vue —— 通用加载指示器
 * =============================================================================
 *
 * Django 对比：
 *   Django 模板中通常用一段 HTML + CSS 动画做 loading 效果
 *   这里封装为可复用的 Vue 组件，可以放在任何页面中
 *
 * 使用方式：
 *   <LoadingSpinner message="帖子加载中..." />
 *   <LoadingSpinner />  （默认显示 "加载中..."）
 */

defineProps({
  /** 加载提示文字，默认 "加载中..." */
  message: {
    type: String,
    default: '加载中...',
  },
})
</script>

<template>
  <div class="spinner-wrapper">
    <!-- 旋转的圆环动画 -->
    <div class="spinner" />
    <!-- 加载提示文字 -->
    <p class="spinner-text">{{ message }}</p>
  </div>
</template>

<style scoped>
.spinner-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 16px;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.spinner-text {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}
</style>