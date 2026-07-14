<script setup>
/**
 * =============================================================================
 *  FavoritesView.vue —— 我的收藏页面
 * =============================================================================
 *
 * Django 对比：Django 中用户收藏通常通过多对多关系实现，
 *   如 User.favorite_posts = ManyToManyField(Post)，
 *   然后在视图中通过 request.user.favorite_posts.all() 获取并分页。
 *   这里前端调用 getFavorites(page, page_size) API 获取分页收藏列表。
 *
 * 路由：/favorites → name: 'favorites'（requiresAuth: true）
 *   未登录用户会被全局路由守卫重定向到登录页。
 *
 * 功能：
 *   1. 分页展示当前用户收藏的帖子列表
 *   2. 复用 PostCard 组件展示每个帖子（含点赞/收藏按钮）
 *   3. PostCard 中的取消收藏操作会触发本地列表更新（移除该项）
 *   4. 空状态：「还没有收藏任何帖子」+ 引导去论坛浏览
 *   5. 加载/错误覆盖
 */
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import PostCard from '@/components/PostCard.vue'
import Pagination from '@/components/Pagination.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const auth = useAuthStore()

// ── 状态 ──────────────────────────────────────────────────────

/** 收藏的帖子列表 */
const posts = ref([])

/** 收藏总数 */
const total = ref(0)

/** 当前页码 */
const page = ref(1)

/** 每页条数 */
const pageSize = 20

/** 是否正在加载 */
const isLoading = ref(true)

/** 错误消息 */
const error = ref('')

// ── 计算属性 ──────────────────────────────────────────────────

/** 总页数 */
const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)

/** 是否有数据 */
const hasData = computed(() => posts.value.length > 0)

// ── API 数据加载 ──────────────────────────────────────────────

/**
 * 获取收藏列表
 * 调用 GET /user/me/favorites?page={page}&page_size={pageSize}
 */
async function fetchFavorites() {
  isLoading.value = true
  error.value = ''
  try {
    const data = await postsApi.getFavorites(page.value, pageSize)
    posts.value = data.posts || []
    total.value = data.total || 0
  } catch (e) {
    error.value = e.message || '加载收藏失败'
  } finally {
    isLoading.value = false
  }
}

// ── 交互事件 ──────────────────────────────────────────────────

/**
 * 收藏状态变更回调（由 PostCard emit）
 * 当用户在收藏页取消收藏某帖子时，从列表中移除该项
 */
function onFavoriteToggled(postId) {
  posts.value = posts.value.filter((p) => p.id !== postId)
  total.value = Math.max(0, total.value - 1)
}

/**
 * 翻页
 */
function goToPage(p) {
  page.value = p
  fetchFavorites()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** 跳转到论坛浏览更多帖子 */
function goToForum() {
  router.push({ name: 'forum' })
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(fetchFavorites)
</script>

<template>
  <section class="forum-container">
    <!-- ── 页面 Header ─────────────────────────────────────── -->
    <div class="forum-header">
      <h2>⭐ 我的收藏</h2>
      <span v-if="total" class="favorites-count">共 {{ total }} 篇</span>
    </div>

    <!-- ── 加载状态 ──────────────────────────────────────── -->
    <LoadingSpinner v-if="isLoading" message="加载收藏列表..." />

    <!-- ── 错误状态 ──────────────────────────────────────── -->
    <div v-else-if="error" class="feedback error">{{ error }}</div>

    <!-- ── 空状态 ────────────────────────────────────────── -->
    <div v-else-if="!hasData" class="empty-state">
      <p class="empty-title">还没有收藏任何帖子</p>
      <p class="empty-hint">
        浏览论坛时点击帖子右侧的 ⭐ 按钮即可收藏，方便以后查看
      </p>
      <button class="btn-primary empty-action" @click="goToForum">
        去论坛逛逛
      </button>
    </div>

    <!-- ── 帖子列表 ──────────────────────────────────────── -->
    <template v-else>
      <div class="post-list">
        <PostCard
          v-for="post in posts"
          :key="post.id"
          :post="post"
          @favorite-toggled="onFavoriteToggled"
        />
      </div>

      <!-- ── 分页 ────────────────────────────────────────── -->
      <Pagination
        v-if="total > pageSize"
        :page="page"
        :total-pages="totalPages"
        @change="goToPage"
      />
    </template>
  </section>
</template>

<style scoped>
/* ── Header ─────────────────────────────────────────────────── */

.favorites-count {
  font-size: 0.88rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* ── 反馈消息 ──────────────────────────────────────────────── */

.feedback.error {
  border-radius: 10px;
  padding: 12px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 0.88rem;
  margin-bottom: 12px;
}

/* ── 空状态 ────────────────────────────────────────────────── */

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--color-text-secondary);
}

.empty-title {
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--color-text);
  margin: 0 0 8px;
}

.empty-hint {
  font-size: 0.9rem;
  margin: 0 0 20px;
  line-height: 1.6;
}

.empty-action {
  margin-top: 4px;
}

/* ── 帖子列表（复用 main.css 的 .post-list） ───────────────── */

.post-list {
  display: grid;
  gap: 12px;
}

/* ── 响应式 ────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .forum-header {
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }
}
</style>