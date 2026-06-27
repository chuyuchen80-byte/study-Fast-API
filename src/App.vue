<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import ForumList from './components/ForumList.vue'
import PostDetail from './components/PostDetail.vue'
import CreatePost from './components/CreatePost.vue'

const API_BASE_URL = 'http://127.0.0.1:8000'
const STORAGE_KEY = 'fastapi-blog-session'
const LEGACY_USER_KEY = 'fastapi-blog-user'

function safeParse(value) {
  if (!value) return null
  try { return JSON.parse(value) } catch { return null }
}

const storedSession = safeParse(localStorage.getItem(STORAGE_KEY))
const legacyUser = safeParse(localStorage.getItem(LEGACY_USER_KEY))

const initialSession = storedSession?.token
  ? storedSession
  : legacyUser ? { user: legacyUser, token: '' } : null

const currentView = ref(initialSession?.token ? 'home' : 'auth')
const currentPostId = ref(null)
const editPostId = ref(null)
const activeTab = ref('login')
const isSubmitting = ref(false)
const currentUser = ref(initialSession?.token ? initialSession.user : null)
const currentToken = ref(initialSession?.token ?? '')

const feedback = reactive({ type: '', message: '' })
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirmPassword: '' })

function setFeedback(type, message) { feedback.type = type; feedback.message = message }
function clearFeedback() { setFeedback('', '') }

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || '请求失败')
  return data
}

async function request(path, { method = 'POST', payload, token } = {}) {
  const headers = {}
  if (payload) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method, headers,
    body: payload ? JSON.stringify(payload) : undefined,
  })
  return parseResponse(response)
}

function persistSession(user, token) {
  currentUser.value = user
  currentToken.value = token
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, token }))
  localStorage.removeItem(LEGACY_USER_KEY)
}

async function handleLogin() {
  clearFeedback(); isSubmitting.value = true
  try {
    const data = await request('/user/login', { payload: loginForm })
    persistSession(data.user, data.access_token)
    currentView.value = 'home'
  } catch (error) {
    setFeedback('error', error.message)
  } finally { isSubmitting.value = false }
}

async function handleRegister() {
  clearFeedback()
  if (registerForm.password !== registerForm.confirmPassword) {
    setFeedback('error', '两次输入的密码不一致'); return
  }
  isSubmitting.value = true
  try {
    const data = await request('/user/register', {
      payload: { username: registerForm.username, password: registerForm.password },
    })
    loginForm.username = registerForm.username
    loginForm.password = registerForm.password
    activeTab.value = 'login'
    setFeedback('success', data.message || '注册成功')
  } catch (error) {
    setFeedback('error', error.message)
  } finally { isSubmitting.value = false }
}

function switchTab(tab) { activeTab.value = tab; clearFeedback() }

function logout() {
  currentUser.value = null; currentToken.value = ''
  currentView.value = 'auth'
  localStorage.removeItem(STORAGE_KEY)
  loginForm.password = ''
  registerForm.password = ''; registerForm.confirmPassword = ''
}

function handleNavigate(view, postId = null) {
  currentView.value = view
  if (postId) currentPostId.value = postId
  if (view === 'create-post') editPostId.value = null
}

function handleEditPost(postId) {
  editPostId.value = postId
  currentView.value = 'create-post'
}

async function restoreSession() {
  if (!currentToken.value) return
  try {
    const user = await request('/user/me', { method: 'GET', token: currentToken.value })
    currentUser.value = user
    currentView.value = 'home'
  } catch { logout() }
}

onMounted(() => { restoreSession() })
</script>

<template>
  <div class="page-shell">
    <!-- 导航栏 -->
    <nav v-if="currentView !== 'auth'" class="app-navbar">
      <div class="nav-brand" @click="handleNavigate('home')">Blog</div>
      <div class="nav-links">
        <button :class="{ active: currentView === 'home' }" @click="handleNavigate('home')">首页</button>
        <button
          :class="{ active: currentView === 'forum' || currentView === 'post-detail' || currentView === 'create-post' }"
          @click="handleNavigate('forum')"
        >论坛</button>
        <button
          :class="{ active: currentView === 'create-post' && !editPostId }"
          @click="handleNavigate('create-post')"
        >发帖</button>
      </div>
      <div class="nav-user">
        <span>{{ currentUser?.username }}</span>
        <button class="ghost-button" @click="logout">退出</button>
      </div>
    </nav>

    <!-- 登录/注册 -->
    <section v-if="currentView === 'auth'" class="auth-layout">
      <div class="auth-card">
        <h1>{{ activeTab === 'login' ? '登录' : '注册' }}</h1>
        <p class="subtitle">{{ activeTab === 'login' ? '欢迎回来，请登录你的账号' : '创建一个新账号' }}</p>

        <div class="tab-switcher">
          <button class="tab-button" :class="{ active: activeTab === 'login' }" @click="switchTab('login')">登录</button>
          <button class="tab-button" :class="{ active: activeTab === 'register' }" @click="switchTab('register')">注册</button>
        </div>

        <div v-if="feedback.message" class="feedback" :class="feedback.type">{{ feedback.message }}</div>

        <form v-if="activeTab === 'login'" class="auth-form" @submit.prevent="handleLogin">
          <label>
            用户名
            <input v-model.trim="loginForm.username" type="text" minlength="3" maxlength="50" required />
          </label>
          <label>
            密码
            <input v-model="loginForm.password" type="password" minlength="6" maxlength="50" required />
          </label>
          <button type="submit" class="submit-button" :disabled="isSubmitting">
            {{ isSubmitting ? '登录中...' : '登录' }}
          </button>
        </form>

        <form v-else class="auth-form" @submit.prevent="handleRegister">
          <label>
            用户名
            <input v-model.trim="registerForm.username" type="text" minlength="3" maxlength="50" required />
          </label>
          <label>
            密码
            <input v-model="registerForm.password" type="password" minlength="6" maxlength="50" required />
          </label>
          <label>
            确认密码
            <input v-model="registerForm.confirmPassword" type="password" minlength="6" maxlength="50" required />
          </label>
          <button type="submit" class="submit-button" :disabled="isSubmitting">
            {{ isSubmitting ? '注册中...' : '注册' }}
          </button>
        </form>
      </div>
    </section>

    <!-- 首页 -->
    <section v-else-if="currentView === 'home'" class="home-layout">
      <div class="home-header">
        <p class="eyebrow">控制台</p>
        <h2>{{ currentUser?.username }}，欢迎回来</h2>
      </div>
      <div class="home-grid">
        <div class="home-card" @click="handleNavigate('forum')">
          <div class="card-icon">📋</div>
          <h3>论坛广场</h3>
          <p>浏览和参与讨论</p>
        </div>
        <div class="home-card" @click="handleNavigate('create-post')">
          <div class="card-icon">✏️</div>
          <h3>发布帖子</h3>
          <p>分享你的想法</p>
        </div>
        <div class="home-card">
          <div class="card-icon">👤</div>
          <h3>个人中心</h3>
          <p>用户名：{{ currentUser?.username }}</p>
        </div>
      </div>
    </section>

    <!-- 论坛列表 -->
    <ForumList
      v-else-if="currentView === 'forum'"
      :token="currentToken"
      @navigate="handleNavigate"
    />

    <!-- 帖子详情 -->
    <PostDetail
      v-else-if="currentView === 'post-detail'"
      :post-id="currentPostId"
      :token="currentToken"
      :current-user="currentUser"
      @navigate="handleNavigate"
      @edit-post="handleEditPost"
    />

    <!-- 发帖/编辑 -->
    <CreatePost
      v-else-if="currentView === 'create-post'"
      :token="currentToken"
      :edit-post-id="editPostId"
      @navigate="handleNavigate"
    />
  </div>
</template>
