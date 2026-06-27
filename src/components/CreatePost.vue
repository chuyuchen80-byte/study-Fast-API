<script setup>
import { onMounted, ref, watch } from 'vue'

const props = defineProps({
  token: { type: String, required: true },
  editPostId: { type: Number, default: null },
})

const emit = defineEmits(['navigate', 'post-created'])

const API_BASE_URL = 'http://127.0.0.1:8000'

const title = ref('')
const content = ref('')
const files = ref([])
const previews = ref([])
const isSubmitting = ref(false)
const isLoadingPost = ref(false)
const error = ref('')
const isEdit = ref(false)

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

// 加载待编辑的帖子
async function loadPost() {
  if (!props.editPostId) return
  isLoadingPost.value = true
  try {
    const post = await request(`/posts/${props.editPostId}`)
    title.value = post.title
    content.value = post.content
    isEdit.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    isLoadingPost.value = false
  }
}

// 文件选择
function handleFileChange(e) {
  const selected = Array.from(e.target.files)
  files.value = [...files.value, ...selected]
  updatePreviews()
}

function removeFile(index) {
  files.value.splice(index, 1)
  updatePreviews()
}

function updatePreviews() {
  previews.value = files.value.map(f => URL.createObjectURL(f))
}

async function submitPost() {
  if (!title.value.trim() || !content.value.trim()) {
    error.value = '标题和内容不能为空'
    return
  }

  isSubmitting.value = true
  error.value = ''

  try {
    if (isEdit.value) {
      // 更新帖子
      const post = await request(`/posts/${props.editPostId}`, {
        method: 'PUT',
        payload: { title: title.value.trim(), content: content.value.trim() },
      })
      emit('post-created', post.id)
      emit('navigate', 'post-detail', post.id)
    } else {
      // 创建帖子（FormData 支持图片上传）
      const formData = new FormData()
      formData.append('title', title.value.trim())
      formData.append('content', content.value.trim())
      files.value.forEach(f => formData.append('files', f))

      const post = await request('/posts/', {
        method: 'POST',
        payload: formData,
        isFormData: true,
      })
      emit('post-created', post.id)
      emit('navigate', 'post-detail', post.id)
    }
  } catch (e) {
    error.value = e.message
  } finally {
    isSubmitting.value = false
  }
}

function goBack() {
  emit('navigate', 'forum')
}

onMounted(() => {
  loadPost()
})

// 清理 blob URLs
watch(files, () => {}, { flush: 'post' })
</script>

<template>
  <div class="forum-container">
    <button class="btn-back" @click="goBack">← 返回论坛</button>

    <div v-if="error" class="feedback error">{{ error }}</div>
    <div v-if="isLoadingPost" class="loading-state">加载帖子中...</div>

    <form v-if="!isLoadingPost" class="create-post-form" @submit.prevent="submitPost">
      <h2>{{ isEdit ? '编辑帖子' : '发布新帖' }}</h2>

      <label>
        标题
        <input
          v-model="title"
          type="text"
          placeholder="输入帖子标题..."
          maxlength="100"
          required
        />
      </label>

      <label>
        内容
        <textarea
          v-model="content"
          placeholder="输入帖子内容..."
          rows="8"
          required
        ></textarea>
      </label>

      <!-- 图片上传 -->
      <div v-if="!isEdit" class="upload-area">
        <label class="upload-label">
          上传图片（可选，支持多张）
          <input type="file" multiple accept="image/*" @change="handleFileChange" />
        </label>

        <!-- 图片预览 -->
        <div v-if="previews.length" class="preview-grid">
          <div v-for="(p, i) in previews" :key="i" class="preview-item">
            <img :src="p" alt="预览" />
            <button type="button" class="btn-remove" @click="removeFile(i)">✕</button>
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button type="button" class="btn-secondary" @click="goBack">取消</button>
        <button type="submit" class="btn-primary" :disabled="isSubmitting">
          {{ isSubmitting ? '发布中...' : isEdit ? '保存修改' : '发布帖子' }}
        </button>
      </div>
    </form>
  </div>
</template>
