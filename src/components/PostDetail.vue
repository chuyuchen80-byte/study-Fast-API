<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  postId: { type: Number, required: true },
  token: { type: String, required: true },
  currentUser: { type: Object, default: null },
})

const emit = defineEmits(['navigate', 'edit-post'])

const API_BASE_URL = 'http://127.0.0.1:8000'
const post = ref(null)
const comments = ref([])
const newComment = ref('')
const isLoading = ref(false)
const isSubmitting = ref(false)
const isDeleting = ref(false)
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

  if (method === 'DELETE' && response.status === 204) return null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || '请求失败')
  }
  return data
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function isOwner() {
  return props.currentUser?.id === post.value?.user?.id
}

async function fetchPost() {
  isLoading.value = true
  error.value = ''
  try {
    post.value = await request(`/posts/${props.postId}`)
    comments.value = await request(`/posts/${props.postId}/comments`)
  } catch (e) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

async function addComment() {
  if (!newComment.value.trim()) return
  isSubmitting.value = true
  error.value = ''
  try {
    const comment = await request(`/posts/${props.postId}/comments`, {
      method: 'POST',
      payload: { content: newComment.value.trim() },
    })
    comments.value.push(comment)
    newComment.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    isSubmitting.value = false
  }
}

async function deletePost() {
  if (!confirm('确定要删除这个帖子吗？')) return
  isDeleting.value = true
  try {
    await request(`/posts/${props.postId}`, { method: 'DELETE' })
    emit('navigate', 'forum')
  } catch (e) {
    error.value = e.message
  } finally {
    isDeleting.value = false
  }
}

function editPost() {
  emit('edit-post', props.postId)
}

function goBack() {
  emit('navigate', 'forum')
}

onMounted(() => {
  fetchPost()
})
</script>

<template>
  <div class="forum-container">
    <button class="btn-back" @click="goBack">← 返回论坛</button>

    <div v-if="error" class="feedback error">{{ error }}</div>
    <div v-if="isLoading" class="loading-state">加载中...</div>

    <template v-if="post && !isLoading">
      <!-- 帖子内容 -->
      <article class="post-detail">
        <header class="post-detail-header">
          <h2>{{ post.title }}</h2>
          <div class="post-detail-meta">
            <span>{{ post.user?.username }}</span>
            <span>{{ formatDate(post.created_at) }}</span>
            <span v-if="post.created_at !== post.updated_at">（已编辑）</span>
          </div>
          <div v-if="isOwner()" class="post-actions">
            <button class="btn-sm" @click="editPost">编辑</button>
            <button class="btn-sm btn-danger" :disabled="isDeleting" @click="deletePost">
              {{ isDeleting ? '删除中...' : '删除' }}
            </button>
          </div>
        </header>

        <div class="post-detail-content">{{ post.content }}</div>

        <!-- 图片 -->
        <div v-if="post.images?.length" class="post-detail-images">
          <img
            v-for="img in post.images"
            :key="img.id"
            :src="API_BASE_URL + img.url"
            :alt="img.filename"
            loading="lazy"
          />
        </div>
      </article>

      <!-- 评论区 -->
      <section class="comments-section">
        <h3>评论 ({{ comments.length }})</h3>

        <!-- 评论列表 -->
        <div v-if="comments.length === 0" class="empty-state">
          <p>暂无评论</p>
        </div>

        <div v-else class="comment-list">
          <div v-for="c in comments" :key="c.id" class="comment-card">
            <div class="comment-header">
              <strong>{{ c.user?.username }}</strong>
              <span class="comment-time">{{ formatDate(c.created_at) }}</span>
            </div>
            <p class="comment-content">{{ c.content }}</p>
          </div>
        </div>

        <!-- 评论输入 -->
        <div class="comment-form">
          <textarea
            v-model="newComment"
            placeholder="写下你的评论..."
            rows="3"
            maxlength="1000"
          ></textarea>
          <button
            class="btn-primary"
            :disabled="isSubmitting || !newComment.trim()"
            @click="addComment"
          >
            {{ isSubmitting ? '发送中...' : '发表评论' }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
