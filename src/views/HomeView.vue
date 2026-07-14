<script setup>
/**
 * =============================================================================
 *  HomeView.vue —— 首页/控制台（v2.0 完整版）
 * =============================================================================
 *
 * Django 对比：Django 的 TemplateView（首页仪表盘模板）
 *
 * 路由：/ → name: 'home'
 *
 * 功能：
 *   1. 欢迎问候（显示用户名或"访客"）
 *   2. Hero 区数据卡片：总帖子数、总评论数、活跃用户数
 *      - 帖子总数来自 GET /posts/?page_size=1 的 total 字段
 *      - 评论数来自 GET /posts/?page_size=5 中各帖子的 comment_count 累加（近似统计）
 *      - 活跃用户数来自 recentPosts 去重作者数（近似统计）
 *   3. "热门帖子"区域：按浏览量排序，取 top 5
 *   4. "最新帖子"区域：最新 5 篇
 *   5. 快捷操作按钮：浏览论坛 → /forum，发布帖子 → /create（或 /login）
 *   6. 空状态：没有任何帖子时的友好提示
 *   7. 加载状态：数据加载中的 spinner
 */
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import { formatDate, formatCount, truncate } from '@/utils/helpers'

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const auth = useAuthStore()

// ── 状态 ──────────────────────────────────────────────────────

/** 最新帖子列表（前 5 篇） */
const recentPosts = ref([])

/** 热门帖子列表（按浏览量排序的前 5 篇） */
const hotPosts = ref([])

/** 帖子总数（从分页 API 的 total 字段获取） */
const totalPosts = ref(0)

/** 是否正在加载数据 */
const isLoading = ref(true)

/** 是否加载出错 */
const loadError = ref(false)

// ── 派生数据 ──────────────────────────────────────────────────

/**
 * 总评论数
 * 从最近 5 篇帖子的 comment_count 累加，作为近似统计展示
 * 更精确的方案需要后端提供单独统计接口，这里作为首页概览已足够
 */
const totalComments = computed(() =>
  recentPosts.value.reduce((sum, p) => sum + (p.comment_count || 0), 0)
)

/**
 * 活跃用户数
 * 从最近 5 篇帖子的作者去重计数，作为近似统计
 */
const activeUsers = computed(() => {
  const ids = new Set(
    recentPosts.value
      .map((p) => p.user?.id)
      .filter(Boolean)
  )
  return ids.size
})

// ── API 数据加载 ──────────────────────────────────────────────

onMounted(async () => {
  isLoading.value = true
  loadError.value = false

  try {
    // 并行获取最新帖子（用于首页展示）和总数（仅要 total 字段）
    const [recentData, countData] = await Promise.allSettled([
      postsApi.getPosts({ page: 1, page_size: 5 }),
      postsApi.getPosts({ page: 1, page_size: 1 }),
    ])

    if (recentData.status === 'fulfilled') {
      recentPosts.value = recentData.value.posts || []
    }
    if (countData.status === 'fulfilled') {
      totalPosts.value = countData.value.total || 0
    }

    // 热门帖子：按 view_count 降序排序前 5 篇
    // 从已有数据中提取，不额外请求
    if (recentPosts.value.length > 0) {
      hotPosts.value = [...recentPosts.value]
        .sort((a, b) => (b.view_count || 0) - (a.view_count || 0))
        .slice(0, 5)
    }
  } catch {
    loadError.value = true
  } finally {
    isLoading.value = false
  }
})

// ── 导航辅助 ──────────────────────────────────────────────────

/** 快捷跳转到发布页面，未登录则跳转登录页 */
function goToCreate() {
  if (auth.isLoggedIn) {
    router.push({ name: 'create-post' })
  } else {
    router.push({ name: 'login', query: { redirect: '/create' } })
  }
}
</script>

<template>
  <section class="home-layout">
    <!-- ── Header 欢迎区 ───────────────────────────────────── -->
    <div class="home-header">
      <p class="eyebrow">控制台</p>
      <h2>{{ auth.isLoggedIn ? `${auth.user?.username}，欢迎回来` : '你好，访客' }}</h2>
      <p class="home-subtitle">
        {{ auth.isLoggedIn ? '看看论坛今天有什么新鲜事' : '登录后即可参与讨论和发布帖子' }}
      </p>
    </div>

    <!-- ── 加载状态 ───────────────────────────────────────── -->
    <div v-if="isLoading" class="loading-state">
      <p>加载中...</p>
    </div>

    <!-- ── 错误状态 ───────────────────────────────────────── -->
    <div v-else-if="loadError" class="error-state">
      <p>加载失败，请刷新页面重试</p>
    </div>

    <!-- ── 主内容区 ───────────────────────────────────────── -->
    <template v-else>
      <!-- ── 数据统计卡片 ───────────────────────────────── -->
      <div class="stats-row">
        <div class="stat-card">
          <span class="stat-icon">📋</span>
          <div class="stat-body">
            <span class="stat-value">{{ formatCount(totalPosts) }}</span>
            <span class="stat-label">帖子总数</span>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-icon">💬</span>
          <div class="stat-body">
            <span class="stat-value">{{ formatCount(totalComments) }}</span>
            <span class="stat-label">评论总数</span>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-icon">👥</span>
          <div class="stat-body">
            <span class="stat-value">{{ activeUsers }}</span>
            <span class="stat-label">活跃用户</span>
          </div>
        </div>
      </div>

      <!-- ── 快捷操作 ──────────────────────────────────── -->
      <div class="quick-actions">
        <button class="action-card" @click="router.push({ name: 'forum' })">
          <span class="action-icon">📖</span>
          <span class="action-title">浏览论坛</span>
          <span class="action-desc">查看全部帖子</span>
        </button>
        <button class="action-card" @click="goToCreate">
          <span class="action-icon">✏️</span>
          <span class="action-title">发布帖子</span>
          <span class="action-desc">分享你的想法</span>
        </button>
      </div>

      <!-- ── 内容区域（两栏） ─────────────────────────── -->
      <div class="home-grid">
        <!-- 热门帖子 -->
        <div class="home-card wide">
          <h3>热门帖子</h3>
          <div v-if="hotPosts.length === 0" class="inline-empty">
            <p>还没有帖子</p>
          </div>
          <ul v-else class="post-link-list">
            <li v-for="post in hotPosts" :key="post.id">
              <router-link :to="{ name: 'post-detail', params: { id: post.id } }">
                {{ post.title }}
              </router-link>
              <span class="meta">
                {{ formatCount(post.view_count) }} 浏览 · {{ formatCount(post.comment_count || 0) }} 评论 · {{ formatCount(post.like_count || 0) }} 赞
              </span>
            </li>
          </ul>
        </div>

        <!-- 最新帖子 -->
        <div class="home-card">
          <h3>最新帖子</h3>
          <div v-if="recentPosts.length === 0" class="inline-empty">
            <p>还没有帖子</p>
          </div>
          <ul v-else class="post-link-list">
            <li v-for="post in recentPosts" :key="post.id">
              <router-link :to="{ name: 'post-detail', params: { id: post.id } }">
                {{ truncate(post.title, 30) }}
              </router-link>
              <span class="meta">
                {{ post.user?.username || '匿名' }} · {{ formatDate(post.created_at) }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* ── 全局布局类由 main.css 提供：.home-layout, .home-header, .home-grid, .home-card 等 ── */

.home-subtitle {
  color: var(--color-text-secondary);
  font-size: 0.95rem;
  margin: 4px 0 0;
}

/* ── 统计卡片行 ──────────────────────────────────────────────── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 20px 24px;
  box-shadow: var(--shadow);
  transition: box-shadow 0.2s ease;
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
}

.stat-icon {
  font-size: 1.6rem;
  flex-shrink: 0;
}

.stat-body {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.02em;
}

.stat-label {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* ── 快捷操作按钮 ────────────────────────────────────────────── */
.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

.action-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 22px 24px;
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.action-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--color-accent);
  transform: translateY(-1px);
}

.action-icon {
  font-size: 1.4rem;
}

.action-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
}

.action-desc {
  font-size: 0.82rem;
  color: var(--color-text-secondary);
}

/* ── 帖子链接列表 ────────────────────────────────────────────── */
.post-link-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.post-link-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border);
  gap: 12px;
}

.post-link-list li:last-child {
  border-bottom: none;
}

.post-link-list a {
  color: var(--color-text);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.95rem;
  transition: color 0.15s ease;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.post-link-list a:hover {
  color: var(--color-accent);
}

.post-link-list .meta {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── 内联空状态 ──────────────────────────────────────────────── */
.inline-empty {
  text-align: center;
  padding: 20px 0;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}

.inline-empty p {
  margin: 0;
}

/* ── 加载/错误状态 ───────────────────────────────────────────── */
.loading-state,
.error-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--color-text-secondary);
}

.loading-state p,
.error-state p {
  font-size: 1rem;
  margin: 0;
}

.error-state {
  color: var(--color-danger);
}

/* ── 响应式 ──────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .stats-row,
  .quick-actions {
    grid-template-columns: 1fr;
  }

  .home-card.wide {
    grid-column: span 1;
  }

  .post-link-list li {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>