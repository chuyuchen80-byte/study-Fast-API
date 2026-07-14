<script setup>
/**
 * =============================================================================
 *  PostCard.vue —— 可复用帖子卡片组件
 * =============================================================================
 *
 * Django 对比：
 *   Django 模板中常有一个 _post_card.html 的 include 片段，在各个页面复用
 *   这里封装为 Vue 组件，放在论坛列表、收藏页、用户主页等处
 *
 * Props:
 *   post: PostResponse 对象（由后端 API 返回的标准帖子结构）
 *
 * 功能：
 *   1. 展示帖子标题、摘要、元数据（作者/时间/互动数）
 *   2. 分类徽章 + 标签药丸 + 置顶/精华标记
 *   3. 缩略图（取第一张图片）
 *   4. 点赞/取消点赞按钮（需登录，使用 postsApi.toggleLike）
 *   5. 收藏/取消收藏按钮（需登录，使用 postsApi.toggleFavorite）
 *   6. 点击卡片跳转到帖子详情页 /post/:id
 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import { formatDate, truncate, getImageUrl, formatCount } from '@/utils/helpers'

// ── Props ──────────────────────────────────────────────────

const props = defineProps({
  /** 帖子数据对象（PostResponse） */
  post: {
    type: Object,
    required: true,
  },
})

// ── Emits ──────────────────────────────────────────────────

const emit = defineEmits({
  /** 点赞状态变更后触发，父组件可据此更新列表 */
  likeToggled: (postId) => typeof postId === 'number',
  /** 收藏状态变更后触发 */
  favoriteToggled: (postId) => typeof postId === 'number',
})

// ── 全局依赖 ──────────────────────────────────────────────

const router = useRouter()
const auth = useAuthStore()

// ── 本地交互状态 ──────────────────────────────────────────

/** 是否已点赞（本地乐观更新） */
const isLiked = ref(false)

/** 点赞数（本地乐观更新，后端返回后同步） */
const likeCount = ref(0)

/** 点赞请求进行中 */
const liking = ref(false)

/** 是否已收藏 */
const isFavorited = ref(false)

/** 收藏数 */
const favoriteCount = ref(0)

/** 收藏请求进行中 */
const favoriting = ref(false)

// ── 初始化 ─────────────────────────────────────────────────

onMounted(async () => {
  // 同步后端已知数据作为初始值
  likeCount.value = props.post.like_count || 0
  isLiked.value = props.post.is_liked || false
  isFavorited.value = props.post.is_favorited || false

  // 如果已登录，从后端获取准确的点赞/收藏状态（覆盖列表接口的数据）
  if (auth.isLoggedIn) {
    try {
      const { liked } = await postsApi.getLikeStatus(props.post.id)
      isLiked.value = liked
    } catch {
      // 未登录或网络问题，忽略
    }
  }
})

// ── 导航 ───────────────────────────────────────────────────

/** 点击卡片跳转到帖子详情 */
function goToDetail() {
  router.push({ name: 'post-detail', params: { id: props.post.id } })
}

// ── 点赞/取消点赞 ──────────────────────────────────────────

/**
 * 切换点赞状态
 * 采用乐观更新：先更新本地 UI，再请求后端
 */
async function toggleLike(e) {
  // 阻止冒泡，避免触发外层卡片的点击导航
  e.stopPropagation()

  if (!auth.isLoggedIn) {
    router.push({ name: 'login', query: { redirect: `/post/${props.post.id}` } })
    return
  }
  if (liking.value) return

  liking.value = true

  // 乐观更新本地状态
  const wasLiked = isLiked.value
  isLiked.value = !wasLiked
  likeCount.value += wasLiked ? -1 : 1

  try {
    const result = await postsApi.toggleLike(props.post.id)
    // 后端返回的标准结构：{ active: boolean, count: number }
    if (result && typeof result.active === 'boolean') {
      isLiked.value = result.active
    }
    if (result && typeof result.count === 'number') {
      likeCount.value = result.count
    }
    emit('likeToggled', props.post.id)
  } catch {
    // 请求失败，回滚本地状态
    isLiked.value = wasLiked
    likeCount.value += wasLiked ? 1 : -1
  } finally {
    liking.value = false
  }
}

// ── 收藏/取消收藏 ──────────────────────────────────────────

/** 切换收藏状态（乐观更新） */
async function toggleFav(e) {
  e.stopPropagation()

  if (!auth.isLoggedIn) {
    router.push({ name: 'login', query: { redirect: `/post/${props.post.id}` } })
    return
  }
  if (favoriting.value) return

  favoriting.value = true
  const wasFav = isFavorited.value
  isFavorited.value = !wasFav

  try {
    const result = await postsApi.toggleFavorite(props.post.id)
    if (result && typeof result.active === 'boolean') {
      isFavorited.value = result.active
    }
    if (result && typeof result.count === 'number') {
      favoriteCount.value = result.count
    }
    emit('favoriteToggled', props.post.id)
  } catch {
    isFavorited.value = wasFav
  } finally {
    favoriting.value = false
  }
}

// ── 辅助计算 ──────────────────────────────────────────────

/** 首张图片的完整 URL（用于缩略图），没有图片返回空字符串 */
function thumbnailUrl() {
  if (props.post.images && props.post.images.length > 0) {
    return getImageUrl(props.post.images[0].url)
  }
  return ''
}

/** 获取分类名称 */
function categoryName() {
  return props.post.category?.name || ''
}
</script>

<template>
  <article class="post-card" @click="goToDetail">
    <!-- ── 正文区域 ──────────────────────────────────── -->
    <div class="post-card-body">
      <!-- 标题行：置顶/精华标记 + 标题 -->
      <h3 class="post-card-title">
        <span v-if="post.is_pinned" class="badge badge-pin">置顶</span>
        <span v-if="post.is_featured" class="badge badge-featured">精华</span>
        {{ post.title }}
      </h3>

      <!-- 内容摘要 -->
      <p class="post-card-content">{{ truncate(post.content, 120) }}</p>

      <!-- 元数据行 -->
      <div class="post-card-meta">
        <span class="meta-author">{{ post.user?.username || '未知用户' }}</span>
        <span class="meta-time">{{ formatDate(post.created_at) }}</span>
        <span class="meta-stat">评论 {{ formatCount(post.comment_count || 0) }}</span>
        <span class="meta-stat">浏览 {{ formatCount(post.view_count || 0) }}</span>
      </div>

      <!-- 标签 & 分类 -->
      <div class="post-card-tags">
        <!-- 分类徽章 -->
        <span v-if="categoryName()" class="badge badge-category">
          {{ categoryName() }}
        </span>
        <!-- 标签药丸 -->
        <span
          v-for="tag in post.tags || []"
          :key="tag.id || tag.name"
          class="badge badge-tag"
        >
          #{{ tag.name || tag }}
        </span>
      </div>
    </div>

    <!-- ── 缩略图 ──────────────────────────────────────── -->
    <div v-if="thumbnailUrl()" class="post-card-thumb">
      <img :src="thumbnailUrl()" alt="封面" loading="lazy" />
    </div>

    <!-- ── 操作按钮列（右侧纵向排列） ──────────────────── -->
    <div class="post-card-actions">
      <!-- 点赞按钮 -->
      <button
        class="action-btn"
        :class="{ active: isLiked }"
        :title="isLiked ? '取消点赞' : '点赞'"
        :disabled="liking"
        @click="toggleLike"
      >
        <span class="action-icon">{{ isLiked ? '❤️' : '🤍' }}</span>
        <span class="action-count">{{ formatCount(likeCount) }}</span>
      </button>

      <!-- 收藏按钮 -->
      <button
        class="action-btn"
        :class="{ active: isFavorited }"
        :title="isFavorited ? '取消收藏' : '收藏'"
        :disabled="favoriting"
        @click="toggleFav"
      >
        <span class="action-icon">{{ isFavorited ? '⭐' : '☆' }}</span>
      </button>
    </div>
  </article>
</template>

<style scoped>
/* ── 卡片主体（使用 main.css 公共类名保持一致性） ──────── */
.post-card {
  display: flex;
  gap: 16px;
  padding: 22px 24px;
  border-radius: var(--radius);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.post-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.post-card-body {
  flex: 1;
  min-width: 0;
}

.post-card-title {
  color: var(--color-text);
  font-size: 1.08rem;
  font-weight: 600;
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.post-card-content {
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  margin: 0 0 10px;
  line-height: 1.5;
}

.post-card-meta {
  display: flex;
  gap: 14px;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.meta-author {
  font-weight: 500;
  color: var(--color-text);
}

/* ── 标签区 ──────────────────────────────────────────────── */
.post-card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 500;
  white-space: nowrap;
}

.badge-pin {
  background: #fef3c7;
  color: #92400e;
}

.badge-featured {
  background: #ede9fe;
  color: #5b21b6;
}

.badge-category {
  background: #e0e7ff;
  color: var(--color-accent);
}

.badge-tag {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

/* ── 缩略图 ──────────────────────────────────────────────── */
.post-card-thumb {
  flex-shrink: 0;
  width: 90px;
  height: 90px;
  border-radius: 8px;
  overflow: hidden;
  background: #f3f4f6;
}

.post-card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ── 操作按钮列 ──────────────────────────────────────────── */
.post-card-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  justify-content: flex-start;
  flex-shrink: 0;
  padding-top: 2px;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  border: 0;
  background: transparent;
  padding: 4px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: all 0.15s ease;
  min-width: 36px;
}

.action-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.action-btn.active {
  color: var(--color-danger);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

.action-icon {
  font-size: 1.1rem;
}

.action-count {
  font-size: 0.7rem;
  font-weight: 500;
}

/* ── 移动端响应：缩略图全宽，操作按钮横向 ──────────────── */
@media (max-width: 768px) {
  .post-card {
    flex-direction: column-reverse;
  }

  .post-card-thumb {
    width: 100%;
    height: 150px;
  }

  .post-card-actions {
    flex-direction: row;
    gap: 12px;
  }
}
</style>