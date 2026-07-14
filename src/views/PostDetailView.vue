<script setup>
/**
 * =============================================================================
 *  PostDetailView.vue —— 帖子详情页面（v2.0 全功能版）
 * =============================================================================
 *
 * Django 对比：Django 的 DetailView（帖子详情视图）
 *
 * 路由：/post/:id → name: 'post-detail'（props: true，id 注入为 prop）
 *
 * 功能：
 *   1. 根据路由参数 id 从 API 获取帖子详情
 *   2. 展示：标题、作者（可点击跳转用户主页）、时间、浏览量、点赞数、分类、标签
 *   3. Markdown 渲染正文（via renderMarkdown）
 *   4. 图片画廊（grid 排版，点击弹窗全屏预览）
 *   5. 操作按钮行：点赞（toggle）、收藏（toggle）、编辑（作者）、删除（作者/管理员 + 二次确认）、置顶/精华切换（管理员）
 *   6. 复用 CommentSection 组件展示评论区
 *   7. 返回按钮 → /forum
 *   8. 加载/错误/404 状态
 */
import { onMounted, reactive, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import { formatDate, formatCount, getImageUrl } from '@/utils/helpers'
import { renderMarkdown } from '@/utils/markdown'
import CommentSection from '@/components/CommentSection.vue'

// ── Props（由路由注入）─────────────────────────────────────────

const props = defineProps({
  /** 帖子 ID（来自路由参数 :id） */
  id: {
    type: [String, Number],
    required: true,
  },
})

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ── 核心数据状态 ──────────────────────────────────────────────

/** 帖子详情对象（PostResponse） */
const post = ref(null)

/** 是否正在加载 */
const isLoading = ref(false)

/** 错误消息 */
const error = ref('')

/** 不存在的帖子（404） */
const isNotFound = ref(false)

// ── 交互操作状态 ──────────────────────────────────────────────

/** 点赞请求进行中 */
const liking = ref(false)

/** 收藏请求进行中 */
const favoriting = ref(false)

/** 删除请求进行中 */
const deleting = ref(false)

/** 置顶切换进行中 */
const pinning = ref(false)

/** 精华切换进行中 */
const featuring = ref(false)

// ── 乐观更新的交互状态 ────────────────────────────────────────

/** 当前用户是否已点赞 */
const isLiked = ref(false)

/** 当前用户是否已收藏 */
const isFavorited = ref(false)

/** 点赞数（本地乐观值） */
const likeCount = ref(0)

/** 收藏数（本地乐观值） */
const favoriteCount = ref(0)

// ── 图片灯箱状态 ──────────────────────────────────────────────

/** 灯箱是否打开 */
const lightboxOpen = ref(false)

/** 灯箱展示的图片索引 */
const lightboxIndex = ref(0)

// ── 权限计算 ──────────────────────────────────────────────────

/** 当前用户是否为帖子作者 */
const isAuthor = computed(() =>
  auth.isLoggedIn && auth.user?.id === post.value?.user?.id
)

/** 当前用户是否可以编辑帖子（仅作者） */
const canEdit = computed(() => isAuthor.value)

/** 当前用户是否可以删除帖子（作者 或 管理员） */
const canDelete = computed(() =>
  isAuthor.value || auth.isAdmin
)

/** 当前用户是否为管理员（可置顶/精华操作） */
const isAdmin = computed(() => auth.isAdmin)

// ── 辅助计算 ──────────────────────────────────────────────────

/** 帖子图片列表（带完整 URL） */
const postImages = computed(() =>
  (post.value?.images || []).map((img) => ({
    ...img,
    fullUrl: getImageUrl(img.url),
  }))
)

// ── API 数据加载 ──────────────────────────────────────────────

/**
 * 获取帖子详情并初始化交互状态
 */
async function fetchPost() {
  const postId = Number(props.id)
  if (!postId || Number.isNaN(postId)) {
    isNotFound.value = true
    return
  }

  isLoading.value = true
  error.value = ''
  isNotFound.value = false

  try {
    const data = await postsApi.getPost(postId)
    post.value = data

    // 初始化互动状态
    isLiked.value = data.is_liked || false
    isFavorited.value = data.is_favorited || false
    likeCount.value = data.like_count || 0
    favoriteCount.value = data.favorite_count || 0

    // 如果登录，验证点赞状态
    if (auth.isLoggedIn) {
      try {
        const { liked } = await postsApi.getLikeStatus(postId)
        isLiked.value = liked
      } catch {
        // 忽略
      }
    }
  } catch (e) {
    if (e.message && (e.message.includes('404') || e.message.includes('不存在'))) {
      isNotFound.value = true
    } else {
      error.value = e.message || '加载帖子失败'
    }
  } finally {
    isLoading.value = false
  }
}

// ── 互动操作 ──────────────────────────────────────────────────

/**
 * 切换点赞（乐观更新）
 */
async function toggleLike() {
  if (!auth.isLoggedIn) {
    router.push({ name: 'login', query: { redirect: `/post/${props.id}` } })
    return
  }
  if (liking.value) return

  liking.value = true
  const wasLiked = isLiked.value
  isLiked.value = !wasLiked
  likeCount.value += wasLiked ? -1 : 1

  try {
    const result = await postsApi.toggleLike(post.value.id)
    if (result && typeof result.active === 'boolean') {
      isLiked.value = result.active
    }
    if (result && typeof result.count === 'number') {
      likeCount.value = result.count
    }
  } catch {
    // 回滚
    isLiked.value = wasLiked
    likeCount.value += wasLiked ? 1 : -1
  } finally {
    liking.value = false
  }
}

/**
 * 切换收藏（乐观更新）
 */
async function toggleFavorite() {
  if (!auth.isLoggedIn) {
    router.push({ name: 'login', query: { redirect: `/post/${props.id}` } })
    return
  }
  if (favoriting.value) return

  favoriting.value = true
  const wasFav = isFavorited.value
  isFavorited.value = !wasFav
  favoriteCount.value += wasFav ? -1 : 1

  try {
    const result = await postsApi.toggleFavorite(post.value.id)
    if (result && typeof result.active === 'boolean') {
      isFavorited.value = result.active
    }
    if (result && typeof result.count === 'number') {
      favoriteCount.value = result.count
    }
  } catch {
    isFavorited.value = wasFav
    favoriteCount.value += wasFav ? 1 : -1
  } finally {
    favoriting.value = false
  }
}

/**
 * 删除帖子（需二次确认）
 */
async function handleDelete() {
  if (!window.confirm('确定要删除这篇帖子吗？此操作不可撤销。')) return

  deleting.value = true
  try {
    await postsApi.deletePost(post.value.id)
    router.push({ name: 'forum' })
  } catch (e) {
    error.value = e.message || '删除失败'
  } finally {
    deleting.value = false
  }
}

/**
 * 跳转编辑页
 */
function handleEdit() {
  router.push({ name: 'edit-post', params: { id: post.value.id } })
}

/**
 * 切换置顶（管理员操作）
 */
async function handleTogglePin() {
  if (!isAdmin.value) return
  pinning.value = true
  try {
    const result = await postsApi.togglePin(post.value.id)
    post.value.is_pinned = result.is_pinned
  } catch (e) {
    error.value = e.message || '操作失败'
  } finally {
    pinning.value = false
  }
}

/**
 * 切换精华（管理员操作）
 */
async function handleToggleFeature() {
  if (!isAdmin.value) return
  featuring.value = true
  try {
    const result = await postsApi.toggleFeature(post.value.id)
    post.value.is_featured = result.is_featured
  } catch (e) {
    error.value = e.message || '操作失败'
  } finally {
    featuring.value = false
  }
}

// ── 图片灯箱 ──────────────────────────────────────────────────

/** 打开灯箱并定位到指定索引 */
function openLightbox(index) {
  lightboxIndex.value = index
  lightboxOpen.value = true
}

/** 关闭灯箱 */
function closeLightbox() {
  lightboxOpen.value = false
}

/** 切换到上一张 */
function prevImage() {
  if (lightboxIndex.value > 0) {
    lightboxIndex.value--
  } else {
    lightboxIndex.value = postImages.value.length - 1
  }
}

/** 切换到下一张 */
function nextImage() {
  if (lightboxIndex.value < postImages.value.length - 1) {
    lightboxIndex.value++
  } else {
    lightboxIndex.value = 0
  }
}

// ── 导航 ──────────────────────────────────────────────────────

/** 返回论坛列表 */
function goBack() {
  router.push({ name: 'forum' })
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(() => {
  fetchPost()
})
</script>

<template>
  <div class="forum-container">
    <!-- ── 返回按钮 ─────────────────────────────────────────── -->
    <button class="btn-back" @click="goBack">&larr; 返回论坛</button>

    <!-- ── 加载状态 ────────────────────────────────────────── -->
    <div v-if="isLoading" class="loading-state">
      <p>帖子加载中...</p>
    </div>

    <!-- ── 404 状态 ────────────────────────────────────────── -->
    <div v-else-if="isNotFound" class="empty-state">
      <p>帖子不存在或已被删除</p>
      <button class="btn-secondary" style="margin-top: 12px" @click="goBack">
        返回论坛
      </button>
    </div>

    <!-- ── 错误状态 ────────────────────────────────────────── -->
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-secondary" style="margin-top: 12px" @click="fetchPost">
        重试
      </button>
    </div>

    <!-- ── 帖子详情主体 ──────────────────────────────────── -->
    <template v-else-if="post">
      <article class="post-detail">
        <!-- ── 标题 ──────────────────────────────────────── -->
        <div class="post-detail-header">
          <h2>
            <span v-if="post.is_pinned" class="badge badge-pin">置顶</span>
            <span v-if="post.is_featured" class="badge badge-featured">精华</span>
            {{ post.title }}
          </h2>
        </div>

        <!-- ── 元数据行 ────────────────────────────────── -->
        <div class="post-detail-meta">
          <span class="meta-author">
            <span
              class="author-link"
              @click="router.push({ name: 'user-profile', params: { id: post.user?.id } })"
            >
              {{ post.user?.username || '匿名用户' }}
            </span>
          </span>
          <span class="meta-time">{{ formatDate(post.created_at) }}</span>
          <span v-if="post.created_at !== post.updated_at" class="meta-edited">
            （已编辑）
          </span>
          <span class="meta-stat">浏览 {{ formatCount(post.view_count || 0) }}</span>
        </div>

        <!-- ── 分类 & 标签 ─────────────────────────────── -->
        <div class="post-detail-tags">
          <span v-if="post.category" class="badge badge-category">
            {{ post.category.name }}
          </span>
          <span
            v-for="tag in post.tags || []"
            :key="tag.id || tag.name"
            class="badge badge-tag"
          >
            #{{ tag.name || tag }}
          </span>
        </div>

        <!-- ── 操作按钮行 ──────────────────────────────── -->
        <div class="post-actions">
          <!-- 点赞按钮 -->
          <button
            class="action-button"
            :class="{ active: isLiked }"
            :disabled="liking"
            @click="toggleLike"
          >
            {{ isLiked ? '❤️' : '🤍' }} {{ isLiked ? '已赞' : '点赞' }}
            （{{ formatCount(likeCount) }}）
          </button>

          <!-- 收藏按钮 -->
          <button
            class="action-button"
            :class="{ active: isFavorited }"
            :disabled="favoriting"
            @click="toggleFavorite"
          >
            {{ isFavorited ? '⭐' : '☆' }} {{ isFavorited ? '已收藏' : '收藏' }}
            （{{ formatCount(favoriteCount) }}）
          </button>

          <!-- 编辑按钮（仅作者） -->
          <button
            v-if="canEdit"
            class="action-button"
            @click="handleEdit"
          >
            ✏️ 编辑
          </button>

          <!-- 删除按钮（作者 / 管理员，带确认） -->
          <button
            v-if="canDelete"
            class="action-button action-danger"
            :disabled="deleting"
            @click="handleDelete"
          >
            {{ deleting ? '删除中...' : '🗑️ 删除' }}
          </button>

          <!-- 管理员操作 -->
          <template v-if="isAdmin">
            <button
              class="action-button admin-action"
              :disabled="pinning"
              @click="handleTogglePin"
            >
              {{ pinning ? '操作中...' : (post.is_pinned ? '📌 取消置顶' : '📌 置顶') }}
            </button>
            <button
              class="action-button admin-action"
              :disabled="featuring"
              @click="handleToggleFeature"
            >
              {{ featuring ? '操作中...' : (post.is_featured ? '✨ 取消精华' : '✨ 设为精华') }}
            </button>
          </template>
        </div>

        <!-- ── Markdown 正文 ───────────────────────────── -->
        <div
          class="post-detail-content"
          v-html="renderMarkdown(post.content)"
        />

        <!-- ── 图片画廊 ────────────────────────────────── -->
        <div v-if="postImages.length > 0" class="post-detail-images">
          <img
            v-for="(img, i) in postImages"
            :key="img.id || i"
            :src="img.fullUrl"
            :alt="`图片 ${i + 1}`"
            loading="lazy"
            @click="openLightbox(i)"
          >
        </div>
      </article>

      <!-- ── 评论区 ────────────────────────────────────── -->
      <CommentSection
        :post-id="post.id"
        :post-author-id="post.user?.id"
      />
    </template>

    <!-- ── 图片灯箱（全屏预览） ──────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="lightboxOpen"
        class="lightbox-overlay"
        @click.self="closeLightbox"
      >
        <button class="lightbox-close" @click="closeLightbox">&times;</button>
        <button
          v-if="postImages.length > 1"
          class="lightbox-nav lightbox-prev"
          @click.stop="prevImage"
        >
          &#8249;
        </button>
        <div class="lightbox-content">
          <img
            :src="postImages[lightboxIndex]?.fullUrl"
            :alt="`图片 ${lightboxIndex + 1}`"
          >
          <p class="lightbox-counter" v-if="postImages.length > 1">
            {{ lightboxIndex + 1 }} / {{ postImages.length }}
          </p>
        </div>
        <button
          v-if="postImages.length > 1"
          class="lightbox-nav lightbox-next"
          @click.stop="nextImage"
        >
          &#8250;
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── 全局类由 main.css 提供：.forum-container, .post-detail, .post-actions 等 ── */

/* ── 帖子详情增强 ────────────────────────────────────────────── */

.post-detail-header h2 {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.post-detail-meta {
  display: flex;
  gap: 16px;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  margin-bottom: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.author-link {
  color: var(--color-accent);
  cursor: pointer;
  font-weight: 500;
  transition: color 0.15s ease;
}

.author-link:hover {
  color: var(--color-accent-hover);
  text-decoration: underline;
}

.meta-edited {
  font-size: 0.78rem;
  opacity: 0.7;
}

/* ── 标签区 ──────────────────────────────────────────────────── */

.post-detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 0.78rem;
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

/* ── 操作按钮 ────────────────────────────────────────────────── */

.post-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.action-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 7px 14px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 0.88rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-button:hover:not(:disabled) {
  background: #f3f4f6;
  color: var(--color-text);
}

.action-button.active {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: rgba(79, 70, 229, 0.05);
}

.action-button:disabled {
  opacity: 0.5;
  cursor: wait;
}

.action-danger:hover:not(:disabled) {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: #fef2f2;
}

.admin-action {
  border-style: dashed;
}

/* ── 正文 Markdown 渲染 ────────────────────────────────────── */

.post-detail-content {
  color: var(--color-text);
  font-size: 1rem;
  line-height: 1.85;
  word-break: break-word;
  margin-bottom: 20px;
}

/* Markdown 内部元素样式（deep selector） */
.post-detail-content :deep(h1),
.post-detail-content :deep(h2),
.post-detail-content :deep(h3) {
  margin: 1.2em 0 0.6em;
  font-weight: 600;
}

.post-detail-content :deep(h1) { font-size: 1.5rem; }
.post-detail-content :deep(h2) { font-size: 1.25rem; }
.post-detail-content :deep(h3) { font-size: 1.1rem; }

.post-detail-content :deep(p) {
  margin: 0 0 1em;
}

.post-detail-content :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.post-detail-content :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 16px;
  border-radius: 10px;
  overflow-x: auto;
  font-size: 0.9em;
  margin: 1em 0;
}

.post-detail-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.post-detail-content :deep(blockquote) {
  border-left: 4px solid var(--color-border);
  padding-left: 16px;
  margin: 1em 0;
  color: var(--color-text-secondary);
}

.post-detail-content :deep(a) {
  color: var(--color-accent);
  text-decoration: underline;
}

.post-detail-content :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 0.5em 0;
}

.post-detail-content :deep(ul),
.post-detail-content :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}

.post-detail-content :deep(li) {
  margin: 0.25em 0;
}

/* ── 图片画廊 ────────────────────────────────────────────────── */

.post-detail-images {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
  margin-top: 20px;
}

.post-detail-images img {
  width: 100%;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  aspect-ratio: 4/3;
  object-fit: cover;
  border: 1px solid var(--color-border);
}

.post-detail-images img:hover {
  transform: scale(1.03);
  box-shadow: var(--shadow-md);
}

/* ── 图片灯箱 ────────────────────────────────────────────────── */

.lightbox-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-close {
  position: absolute;
  top: 20px;
  right: 30px;
  border: 0;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 2rem;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
  z-index: 1001;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.25);
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 2.5rem;
  width: 50px;
  height: 80px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  transition: background 0.15s ease;
  z-index: 1001;
}

.lightbox-nav:hover {
  background: rgba(255, 255, 255, 0.22);
}

.lightbox-prev {
  left: 16px;
}

.lightbox-next {
  right: 16px;
}

.lightbox-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 90vw;
  max-height: 90vh;
}

.lightbox-content img {
  max-width: 90vw;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 8px;
}

.lightbox-counter {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
  margin-top: 12px;
}

/* ── 加载/错误/404 状态 ─────────────────────────────────────── */

.loading-state,
.empty-state,
.error-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--color-text-secondary);
}

.loading-state p,
.empty-state p,
.error-state p {
  font-size: 1rem;
  margin: 0;
}

.error-state {
  color: var(--color-danger);
}

/* ── 响应式 ──────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .post-detail-images {
    grid-template-columns: 1fr;
  }

  .post-actions {
    flex-direction: column;
  }

  .lightbox-nav {
    width: 40px;
    height: 60px;
    font-size: 1.8rem;
  }
}
</style>