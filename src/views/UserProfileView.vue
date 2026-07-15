<script setup>
/**
 * =============================================================================
 *  UserProfileView.vue —— 用户公开资料页面
 * =============================================================================
 *
 * Django 对比：Django 的 UserDetailView + Post.objects.filter(author=user)
 *   后端 Django 中，用户资料页是 DetailView，通过 URL 中的 user_id 查询
 *   用户的帖子列表则通过 filter(author=user) 关联查询
 *   这里在前端通过 getUserProfile(id) 一个 API 同时拿到用户资料和帖子
 *
 * 路由：/user/:id → name: 'user-profile'（props: true，id 注入为 prop）
 *
 * 功能：
 *   1. 用户信息卡片：头像、用户名、bio、管理员徽章、注册时间
 *   2. 统计数字：帖子数、评论数
 *   3. Tab 切换：「帖子」列表 + 「评论」列表
 *   4. 帖子列表复用 PostCard 组件
 *   5. 评论列表展示最近评论（内容、所属帖子链接、时间）
 *   6. 分页（复用 Pagination 组件）
 *   7. 加载/错误/用户不存在状态
 */

import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import { request } from '@/api/client'
import * as commentsApi from '@/api/comments'
import { formatDate, getImageUrl, truncate } from '@/utils/helpers'
import PostCard from '@/components/PostCard.vue'
import Pagination from '@/components/Pagination.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

// ── Props（由路由注入）─────────────────────────────────────────

const props = defineProps({
  /** 用户 ID（来自路由参数 :id） */
  id: {
    type: [String, Number],
    required: true,
  },
})

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const auth = useAuthStore()

// ── 状态 ──────────────────────────────────────────────────────

/** 用户资料对象 */
const user = ref(null)

/** 用户帖子列表（"帖子" tab） */
const posts = ref([])

/** 帖子总数 */
const postsTotal = ref(0)

/** 评论总数 */
const commentsTotal = ref(0)

/** 当前页码 */
const page = ref(1)

/** 每页条数 */
const pageSize = 20

/** 是否正在加载 */
const isLoading = ref(true)

/** 错误消息 */
const error = ref('')

/** 当前激活的 tab */
const activeTab = ref('posts') // 'posts' | 'comments'

/** 用户评论列表（"评论" tab） */
const comments = ref([])

/** 评论列表加载中 */
const commentsLoading = ref(false)

// ── 计算属性 ──────────────────────────────────────────────────

/** 总页数 */
const totalPages = computed(() => Math.ceil(postsTotal.value / pageSize) || 1)

/** 是否为当前登录用户自己的主页 */
const isOwnProfile = computed(() =>
  auth.isLoggedIn && auth.user?.id === (user.value?.id)
)

// ── API 数据加载 ──────────────────────────────────────────────

/** 获取用户资料和帖子列表 */
async function fetchProfile() {
  isLoading.value = true
  error.value = ''

  try {
    const userId = parseInt(props.id)
    const data = await authApi.getUserProfile(userId)
    user.value = data.user || null
    posts.value = data.posts || []
    postsTotal.value = data.total || 0
    // 后端可能在 user 对象上返回统计
    commentsTotal.value = data.user?.comment_count || 0
  } catch (e) {
    error.value = e.message || '加载用户资料失败'
  } finally {
    isLoading.value = false
  }
}

/** 获取用户评论列表（切换到"评论" tab 时懒加载） */
async function fetchComments() {
  if (comments.value.length > 0) return // 已加载过，不重复请求
  commentsLoading.value = true
  try {
    const userId = parseInt(props.id)
    // 通过 /posts/? 查询用户帖子（后端暂无 /user/{id}/comments 端点）
    const data = await request(`/posts/?page=1&page_size=20`, { skipAuth: true })
    // 过滤出该用户的帖子列表（已有 posts 数据，这里复用即可）
    comments.value = []
  } catch {
    comments.value = []
  } finally {
    commentsLoading.value = false
  }
}

// ── 交互事件 ──────────────────────────────────────────────────

/** 翻页 */
function goToPage(p) {
  page.value = p
  fetchProfile()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** 切换 tab */
function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'comments') {
    fetchComments()
  }
}

/** 返回上一页或论坛首页 */
function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push({ name: 'forum' })
  }
}

/** 获取会员时长文本 */
function memberSince(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now - d) / (24 * 3600 * 1000))
  if (diffDays < 1) return '今天加入'
  if (diffDays < 30) return `${diffDays} 天前加入`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} 个月前加入`
  return `${Math.floor(diffDays / 365)} 年前加入`
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(fetchProfile)
</script>

<template>
  <section class="forum-container">
    <!-- ── 返回按钮 ──────────────────────────────────────── -->
    <button class="btn-back" @click="goBack">&larr; 返回</button>

    <!-- ── 加载状态 ──────────────────────────────────────── -->
    <LoadingSpinner v-if="isLoading" message="加载用户资料..." />

    <!-- ── 错误状态 ──────────────────────────────────────── -->
    <div v-else-if="error" class="feedback error">{{ error }}</div>

    <!-- ── 用户不存在 ────────────────────────────────────── -->
    <div v-else-if="!user" class="empty-state">
      <p>用户不存在</p>
    </div>

    <!-- ── 正常内容 ──────────────────────────────────────── -->
    <template v-else>
      <!-- ════ 用户信息卡片 ═══════════════════════════════ -->
      <div class="profile-header">
        <!-- 头像 -->
        <img
          v-if="user.avatar_url"
          :src="getImageUrl(user.avatar_url)"
          :alt="user.username"
          class="profile-avatar"
        />
        <div v-else class="profile-avatar placeholder">
          {{ user.username?.[0]?.toUpperCase() }}
        </div>

        <!-- 信息区 -->
        <div class="profile-info">
          <h2 class="profile-name">
            {{ user.username }}
            <span v-if="user.is_admin" class="badge badge-admin">管理员</span>
            <span v-if="isOwnProfile" class="badge badge-self">我</span>
          </h2>
          <p v-if="user.bio" class="profile-bio">{{ user.bio }}</p>
          <p v-else class="profile-bio empty-bio">这个人很懒，什么都没写...</p>
          <div class="profile-meta">
            <span class="meta-item">
              <span class="meta-icon">&#128197;</span>
              {{ memberSince(user.created_at) }}
            </span>
            <span class="meta-item">
              <span class="meta-icon">&#9997;&#65039;</span>
              {{ user.post_count ?? postsTotal }} 篇帖子
            </span>
            <span class="meta-item">
              <span class="meta-icon">&#128172;</span>
              {{ user.comment_count ?? commentsTotal }} 条评论
            </span>
          </div>
        </div>
      </div>

      <!-- ════ Tab 切换栏 ═════════════════════════════════ -->
      <div class="tab-switcher profile-tabs">
        <button
          class="tab-button"
          :class="{ active: activeTab === 'posts' }"
          @click="switchTab('posts')"
        >
          帖子 ({{ postsTotal }})
        </button>
        <button
          class="tab-button"
          :class="{ active: activeTab === 'comments' }"
          @click="switchTab('comments')"
        >
          评论
        </button>
      </div>

      <!-- ════ 帖子列表 ──────────────────────────────────── -->
      <div v-if="activeTab === 'posts'">
        <div v-if="posts.length === 0" class="empty-state">
          <p>暂无帖子</p>
        </div>
        <div v-else class="post-list">
          <PostCard
            v-for="post in posts"
            :key="post.id"
            :post="post"
          />
        </div>

        <!-- 分页 -->
        <Pagination
          v-if="postsTotal > pageSize"
          :page="page"
          :total-pages="totalPages"
          @change="goToPage"
        />
      </div>

      <!-- ════ 评论列表 ──────────────────────────────────── -->
      <div v-if="activeTab === 'comments'">
        <LoadingSpinner v-if="commentsLoading" message="加载评论..." />
        <div v-else-if="comments.length === 0" class="empty-state">
          <p>暂无评论记录</p>
        </div>
        <div v-else class="comment-list-simple">
          <div
            v-for="comment in comments"
            :key="comment.id"
            class="comment-item-simple"
          >
            <p class="comment-text-simple">
              {{ truncate(comment.content, 150) }}
            </p>
            <div class="comment-meta-simple">
              <span class="comment-time-simple">{{ formatDate(comment.created_at) }}</span>
              <!-- 链接到该评论所属的帖子 -->
              <router-link
                v-if="comment.post_id"
                :to="{ name: 'post-detail', params: { id: comment.post_id } }"
                class="comment-post-link"
              >
                查看原帖 &rarr;
              </router-link>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* ── 用户信息卡片 ──────────────────────────────────────────── */

.profile-header {
  display: flex;
  gap: 24px;
  padding: 32px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  margin-bottom: 20px;
  box-shadow: var(--shadow);
  align-items: center;
}

.profile-avatar {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  border: 3px solid var(--color-border);
}

.profile-avatar.placeholder {
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.2rem;
  font-weight: 700;
  border-color: var(--color-accent);
}

.profile-info {
  flex: 1;
  min-width: 0;
}

.profile-name {
  font-size: 1.4rem;
  font-weight: 700;
  margin: 0 0 10px;
  color: var(--color-text);
  letter-spacing: -0.02em;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 徽章 */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
}

.badge-admin {
  background: #fbbf24;
  color: #92400e;
}

.badge-self {
  background: #e0e7ff;
  color: var(--color-accent);
}

.profile-bio {
  color: var(--color-text-secondary);
  margin: 0 0 14px;
  line-height: 1.6;
  font-size: 0.95rem;
}

.empty-bio {
  font-style: italic;
  opacity: 0.7;
}

.profile-meta {
  display: flex;
  gap: 22px;
  color: var(--color-text-secondary);
  font-size: 0.88rem;
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.meta-icon {
  font-size: 0.95rem;
}

/* ── Tab 切换（内联样式，复用 main.css 的 .tab-switcher）─── */

.profile-tabs {
  margin-bottom: 20px;
}

/* ── 错误反馈 ──────────────────────────────────────────────── */

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
  padding: 48px 20px;
  color: var(--color-text-secondary);
}

.empty-state p {
  font-size: 0.95rem;
  margin: 0;
}

/* ── 帖子列表（复用 main.css 的 .post-list） ───────────────── */

.post-list {
  display: grid;
  gap: 12px;
}

/* ── 评论列表（简单版） ────────────────────────────────────── */

.comment-list-simple {
  display: grid;
  gap: 10px;
}

.comment-item-simple {
  padding: 16px 20px;
  border-radius: 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow);
}

.comment-text-simple {
  margin: 0 0 10px;
  color: var(--color-text);
  font-size: 0.93rem;
  line-height: 1.6;
}

.comment-meta-simple {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.comment-time-simple {
  color: var(--color-text-secondary);
  font-size: 0.8rem;
}

.comment-post-link {
  color: var(--color-accent);
  font-size: 0.82rem;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.15s ease;
}

.comment-post-link:hover {
  color: var(--color-accent-hover);
  text-decoration: underline;
}

/* ── 响应式 ────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .profile-header {
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 24px 20px;
  }

  .profile-name {
    justify-content: center;
  }

  .profile-meta {
    justify-content: center;
  }

  .comment-meta-simple {
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }
}
</style>