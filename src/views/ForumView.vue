<script setup>
/**
 * =============================================================================
 *  ForumView.vue —— 论坛帖子列表页面（v2.0 全功能版）
 * =============================================================================
 *
 * Django 对比：Django 的 ListView（帖子列表视图）
 *
 * 路由：/forum → name: 'forum'
 *
 * 功能：
 *   1. 搜索栏（debounced 300ms）—— 通过 q 参数搜索
 *   2. 分类过滤药丸 —— 拉取全部分类，"全部" + 各分类，点击筛选
 *   3. 排序标签：最新（默认）、热门（按浏览量）、精华（is_featured）
 *   4. 帖子列表（复用 PostCard 组件）
 *   5. 底部分页（复用 Pagination 组件）
 *   6. "发布新帖"按钮（仅已登录显示）
 *   7. 空状态：\"暂无帖子\"
 *   8. 加载/错误状态
 */
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import * as categoriesApi from '@/api/categories'
import PostCard from '@/components/PostCard.vue'
import Pagination from '@/components/Pagination.vue'

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ── 查询参数（从路由 query 同步）─────────────────────────────

/**
 * 搜索关键词（从 URL query 读取/写入）
 * 通过 watch 监听变化重新请求
 */
const searchQuery = ref(route.query.q || '')

/** 当前页码 */
const currentPage = ref(Number(route.query.page) || 1)

/** 每页条数 */
const pageSize = 20

/** 当前激活的分类 ID（null 表示全部） */
const activeCategoryId = ref(
  route.query.category_id ? Number(route.query.category_id) : null
)

/**
 * 排序方式：
 *  'latest'   → 默认排序（created_at 降序）
 *  'hot'      → 按 view_count 降序（模拟）
 *  'featured' → 只看精华帖（后端筛选）
 */
const activeSort = ref(route.query.sort || 'latest')

// ── 分类列表 ──────────────────────────────────────────────────

const categories = ref([])

// ── 帖子数据 ──────────────────────────────────────────────────

/** 帖子列表 */
const posts = ref([])

/** 帖子总数 */
const total = ref(0)

/** 总页数 */
const totalPages = ref(0)

/** 是否正在加载 */
const isLoading = ref(false)

/** 错误消息 */
const error = ref('')

// ── 搜索防抖 ──────────────────────────────────────────────────

let debounceTimer = null

// ── API 数据加载 ──────────────────────────────────────────────

/**
 * 根据当前查询参数请求帖子列表
 *
 * 排序策略：
 *   latest   → getPosts({ page, page_size, q, category_id })
 *   hot      → 同上但前端按 view_count 排序（后端返回的已含浏览数）
 *   featured → getPosts({ page, page_size, q, category_id }) + 前端只取 is_featured
 *
 * 注：更理想的方案是后端支持 ?sort=hot / ?is_featured=true 参数，
 *     这里前端模式意味着分页不够精确，但满足当前需求。
 */
async function fetchPosts() {
  isLoading.value = true
  error.value = ''

  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize,
    }
    // 搜索关键词
    if (searchQuery.value.trim()) {
      params.q = searchQuery.value.trim()
    }
    // 分类过滤
    if (activeCategoryId.value) {
      params.category_id = activeCategoryId.value
    }

    const data = await postsApi.getPosts(params)
    let list = data.posts || []

    // 前端排序（在服务端支持 sort 参数前）
    if (activeSort.value === 'hot') {
      list = [...list].sort((a, b) => (b.view_count || 0) - (a.view_count || 0))
    } else if (activeSort.value === 'featured') {
      list = list.filter((p) => p.is_featured)
    }

    posts.value = list
    total.value = data.total || list.length
    totalPages.value = Math.ceil(total.value / pageSize) || 1
  } catch (e) {
    error.value = e.message || '加载帖子失败'
  } finally {
    isLoading.value = false
  }
}

/**
 * 获取分类列表
 */
async function fetchCategories() {
  try {
    categories.value = await categoriesApi.getCategories()
  } catch {
    // 分类加载失败不影响帖子列表展示
  }
}

// ── 同步 URL 查询参数 ─────────────────────────────────────────

/**
 * 将当前状态写入 URL query，保证搜索/筛选可分享
 */
function syncQueryParams() {
  const query = {}
  if (searchQuery.value.trim()) query.q = searchQuery.value.trim()
  if (currentPage.value > 1) query.page = currentPage.value
  if (activeCategoryId.value) query.category_id = activeCategoryId.value
  if (activeSort.value !== 'latest') query.sort = activeSort.value

  router.replace({ query })
}

// ── 交互事件 ──────────────────────────────────────────────────

/** 搜索（带 300ms 防抖） */
function onSearchInput(e) {
  const val = e.target.value
  // 清除之前的定时器
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    searchQuery.value = val
    currentPage.value = 1  // 搜索重置到第一页
    syncQueryParams()
    fetchPosts()
  }, 300)
}

/** 选择分类（药丸点击） */
function selectCategory(categoryId) {
  activeCategoryId.value = categoryId === activeCategoryId.value ? null : categoryId
  currentPage.value = 1
  syncQueryParams()
  fetchPosts()
}

/** 切换排序方式 */
function selectSort(sort) {
  activeSort.value = sort
  currentPage.value = 1
  syncQueryParams()
  fetchPosts()
}

/** 翻页 */
function onPageChange(page) {
  currentPage.value = page
  syncQueryParams()
  fetchPosts()
  // 滚动到顶部
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** 跳转创建帖子 */
function goToCreate() {
  if (auth.isLoggedIn) {
    router.push({ name: 'create-post' })
  } else {
    router.push({ name: 'login', query: { redirect: '/create' } })
  }
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(() => {
  fetchCategories()
  fetchPosts()
})
</script>

<template>
  <section class="forum-container">
    <!-- ── Header ───────────────────────────────────────────── -->
    <div class="forum-header">
      <div>
        <h2>论坛广场</h2>
        <p class="forum-subtitle">浏览、搜索和参与讨论</p>
      </div>
      <button
        v-if="auth.isLoggedIn"
        class="btn-primary"
        @click="goToCreate"
      >
        + 发布新帖
      </button>
    </div>

    <!-- ── 搜索栏 ─────────────────────────────────────────── -->
    <div class="search-bar">
      <span class="search-icon">&#128269;</span>
      <input
        :value="searchQuery"
        type="text"
        class="search-input"
        placeholder="搜索帖子标题或内容..."
        @input="onSearchInput"
      >
    </div>

    <!-- ── 分类过滤药丸 ─────────────────────────────────── -->
    <div class="category-pills">
      <button
        class="pill"
        :class="{ active: !activeCategoryId }"
        @click="selectCategory(null)"
      >
        全部
      </button>
      <button
        v-for="cat in categories"
        :key="cat.id"
        class="pill"
        :class="{ active: activeCategoryId === cat.id }"
        @click="selectCategory(cat.id)"
      >
        {{ cat.name }}
      </button>
    </div>

    <!-- ── 排序标签 ──────────────────────────────────────── -->
    <div class="sort-tabs">
      <button
        class="sort-tab"
        :class="{ active: activeSort === 'latest' }"
        @click="selectSort('latest')"
      >
        最新
      </button>
      <button
        class="sort-tab"
        :class="{ active: activeSort === 'hot' }"
        @click="selectSort('hot')"
      >
        热门
      </button>
      <button
        class="sort-tab"
        :class="{ active: activeSort === 'featured' }"
        @click="selectSort('featured')"
      >
        精华
      </button>
    </div>

    <!-- ── 错误提示 ──────────────────────────────────────── -->
    <div v-if="error" class="feedback error">{{ error }}</div>

    <!-- ── 加载状态 ──────────────────────────────────────── -->
    <div v-if="isLoading" class="loading-state">
      <p>帖子加载中...</p>
    </div>

    <!-- ── 空状态 ────────────────────────────────────────── -->
    <div v-else-if="posts.length === 0" class="empty-state">
      <p>暂无帖子</p>
      <p class="empty-hint">
        {{ searchQuery || activeCategoryId ? '换个关键词或分类试试' : '成为第一个发帖的人吧' }}
      </p>
      <button
        v-if="!searchQuery && !activeCategoryId"
        class="btn-primary empty-action"
        @click="goToCreate"
      >
        发布第一篇帖子
      </button>
    </div>

    <!-- ── 帖子列表 ──────────────────────────────────────── -->
    <template v-else>
      <div class="post-list">
        <PostCard
          v-for="post in posts"
          :key="post.id"
          :post="post"
        />
      </div>

      <!-- ── 分页 ────────────────────────────────────────── -->
      <Pagination
        :page="currentPage"
        :total-pages="totalPages"
        @change="onPageChange"
      />
    </template>
  </section>
</template>

<style scoped>
/* ── 全局类由 main.css 提供：.forum-container, .forum-header, .btn-primary, .post-list 等 ── */

/* ── 搜索栏 ──────────────────────────────────────────────────── */
.search-bar {
  position: relative;
  margin-bottom: 18px;
}

.search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1rem;
  color: var(--color-text-secondary);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 12px 14px 12px 42px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.95rem;
  outline: none;
  box-shadow: var(--shadow);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.search-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

/* ── 分类过滤药丸 ────────────────────────────────────────────── */
.category-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.pill {
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 6px 16px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pill:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.pill.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
}

/* ── 排序标签 ────────────────────────────────────────────────── */
.sort-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0;
}

.sort-tab {
  border: 0;
  background: transparent;
  padding: 8px 18px;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s ease;
  margin-bottom: -1px;
}

.sort-tab:hover {
  color: var(--color-text);
}

.sort-tab.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

/* ── 反馈/加载/空状态（配合 main.css） ─────────────────────── */

.feedback.error {
  border-radius: 10px;
  padding: 12px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 0.88rem;
  margin-bottom: 12px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--color-text-secondary);
}

.empty-state p {
  font-size: 0.95rem;
  margin: 0 0 8px;
}

.empty-hint {
  font-size: 0.85rem !important;
  opacity: 0.7;
}

.empty-action {
  margin-top: 16px;
}

/* ── 响应式 ──────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .forum-header {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }

  .sort-tabs {
    overflow-x: auto;
  }

  .category-pills {
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 4px;
  }
}
</style>