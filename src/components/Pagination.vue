<script setup>
/**
 * =============================================================================
 *  Pagination.vue —— 通用分页组件
 * =============================================================================
 *
 * Django 对比：
 *   Django 的 Paginator 类 + 模板中的 page_obj 循环
 *   这里封装为 Vue 组件，emit('change', pageNum) 通知父组件切换页码
 *
 * 使用方式：
 *   <Pagination :page="currentPage" :totalPages="totalPages" @change="onPageChange" />
 *
 * 显示规则：
 *   总页数 <= 7 → 显示所有页码
 *   总页数 > 7 → 显示首尾 + 当前页附近 + 省略号
 */

import { computed } from 'vue'

const props = defineProps({
  /** 当前页码（1-based） */
  page: {
    type: Number,
    required: true,
  },
  /** 总页数 */
  totalPages: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits({
  /** fire when user clicks a page button */
  change: (newPage) => typeof newPage === 'number' && newPage >= 1,
})

/**
 * 计算要显示的页码数组（支持省略号）
 *
 * 策略：
 *   总页数 <= 7 → 全部显示 [1,2,3,4,5,6,7]
 *   总页数 > 7 → 显示首尾 + 当前附近，省略号用 0 占位
 *   如当前在第 5 页共 20 页：[1, 0, 4, 5, 6, 0, 20]（0=省略号）
 */
const pageNumbers = computed(() => {
  const total = props.totalPages
  const current = props.page

  // 总页数少，全部显示
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const pages = []

  // 首页始终显示
  pages.push(1)

  // 计算当前页附近的范围
  let start = Math.max(2, current - 1)
  let end = Math.min(total - 1, current + 1)

  // 如果当前页靠近开头，多显示后面的页
  if (current <= 3) {
    end = Math.min(5, total - 1)
  }
  // 如果当前页靠近结尾，多显示前面的页
  if (current >= total - 2) {
    start = Math.max(2, total - 4)
  }

  // 前面需要省略号
  if (start > 2) {
    pages.push(0) // 0 表示省略号
  }

  // 中间页码
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  // 后面需要省略号
  if (end < total - 1) {
    pages.push(0)
  }

  // 末页始终显示
  pages.push(total)

  return pages
})

function goTo(targetPage) {
  if (targetPage < 1 || targetPage > props.totalPages) return
  if (targetPage === props.page) return
  emit('change', targetPage)
}
</script>

<template>
  <div v-if="totalPages > 1" class="pagination">
    <!-- 上一页 -->
    <button
      class="page-btn"
      :disabled="page <= 1"
      @click="goTo(page - 1)"
    >
      上一页
    </button>

    <!-- 页码按钮 -->
    <template v-for="p in pageNumbers" :key="p">
      <!-- 省略号占位 -->
      <span v-if="p === 0" class="ellipsis">...</span>
      <!-- 正常页码 -->
      <button
        v-else
        class="page-btn"
        :class="{ active: p === page }"
        @click="goTo(p)"
      >
        {{ p }}
      </button>
    </template>

    <!-- 下一页 -->
    <button
      class="page-btn"
      :disabled="page >= totalPages"
      @click="goTo(page + 1)"
    >
      下一页
    </button>
  </div>
</template>

<style scoped>
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  margin-top: 24px;
  flex-wrap: wrap;
}

.page-btn {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 7px 13px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-weight: 500;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.page-btn:hover:not(:disabled):not(.active) {
  background: #f3f4f6;
  color: var(--color-text);
}

.page-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
  cursor: default;
}

.page-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 34px;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  user-select: none;
}
</style>