<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  token: { type: String, required: true },
})

const emit = defineEmits(['navigate'])

const API_BASE_URL = 'http://127.0.0.1:8000'
const posts = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const totalPages = ref(0)
const isLoading = ref(false)
const error = ref('')

async function request(path, { method = 'GET', payload, isFormData = false } = {}) {
  const headers = {}
  if (!isFormData) {
    headers['Content-Type'] = 'application/json'
  }
  if (props.token) {
    headers.Authorization = `Bearer ${props.token}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isFormData ? payload : payload ? JSON.stringify(payload) : undefined,
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || '请求失败')
  }
  return data
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now - d
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function truncate(text, maxLen = 120) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

async function fetchPosts() {
  isLoading.value = true
  error.value = ''
  try {
    const data = await request(`/posts/?page=${page.value}&page_size=${pageSize}`)
    posts.value = data.posts
    total.value = data.total
    totalPages.value = Math.ceil(data.total / pageSize)
  } catch (e) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

function goToPage(p) {
  page.value = p
  fetchPosts()
}

function openPost(postId) {
  emit('navigate', 'post-detail', postId)
}

function goCreate() {
  emit('navigate', 'create-post')
}

onMounted(() => {
  fetchPosts()
})
</script>

<template>
  <div class="forum-container">
    <div class="forum-header">
      <div>
        <h2>论坛</h2>
        <p class="forum-subtitle">共 {{ total }} 个帖子</p>
      </div>
      <button class="btn-primary" @click="goCreate">+ 发布新帖</button>
    </div>

    <div v-if="error" class="feedback error">{{ error }}</div>

    <!-- 加载中 -->
    <div v-if="isLoading" class="loading-state">加载中...</div>

    <!-- 空状态 -->
    <div v-else-if="posts.length === 0" class="empty-state">
      <p>还没有帖子，快来发布第一个吧！</p>
    </div>

    <!-- 帖子列表 -->
    <div v-else class="post-list">
      <article
        v-for="post in posts"
        :key="post.id"
        class="post-card"
        @click="openPost(post.id)"
      >
        <div class="post-card-body">
          <h3 class="post-card-title">{{ post.title }}</h3>
          <p class="post-card-content">{{ truncate(post.content) }}</p>
          <div class="post-card-meta">
            <span class="post-author">{{ post.user?.username || '未知用户' }}</span>
            <span class="post-time">{{ formatDate(post.created_at) }}</span>
            <span class="post-comments">{{ post.comment_count }} 条评论</span>
          </div>
        </div>
        <div v-if="post.images?.length" class="post-card-thumb">
          <img :src="API_BASE_URL + post.images[0].url" alt="封面" />
        </div>
      </article>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination">
      <button :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
      <span v-for="p in totalPages" :key="p">
        <button
          :class="{ active: p === page }"
          @click="goToPage(p)"
        >{{ p }}</button>
      </span>
      <button :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
    </div>
  </div>
</template>
