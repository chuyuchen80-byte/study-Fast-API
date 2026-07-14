<script setup>
/**
 * =============================================================================
 *  AuthView.vue —— 登录/注册页面（v2.0 全功能版）
 * =============================================================================
 *
 * Django 对比：Django 的 LoginView + RegisterView（或 django-allauth）
 *
 * 路由：
 *   /login    → name: 'login',    props: { defaultTab: 'login' }
 *   /register → name: 'register', props: { defaultTab: 'register' }
 *
 * 功能：
 *   1. 两栏 tab 切换 —— "登录" 和 "注册"
 *   2. 登录表单：用户名 + 密码，调用 useAuthStore().login()
 *      成功后重定向到 home 或 route.query.redirect
 *   3. 注册表单：用户名 + 密码 + 确认密码
 *      成功后自动切换到登录 tab 并提示
 *   4. 客户端校验：密码至少 6 位、两次密码一致
 *   5. 全局样式复用 main.css 的 .auth-layout / .auth-card / .tab-switcher 等类
 *   6. 已登录用户由路由守卫（router.beforeEach meta.guest）拦截重定向，
 *      组件层面不做额外处理
 */
import { reactive, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// ── Props（由路由定义注入）─────────────────────────────────────

const props = defineProps({
  /** 默认激活的 tab：'login' 或 'register' */
  defaultTab: {
    type: String,
    default: 'login',
  },
})

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ── 本地状态 ──────────────────────────────────────────────────

/** 当前激活的 tab */
const activeTab = ref(props.defaultTab)

/** 表单提交中（防止重复点击） */
const isSubmitting = ref(false)

/** 操作反馈 { type: 'success'|'error', message: string } */
const feedback = reactive({ type: '', message: '' })

/** 登录表单数据 */
const loginForm = reactive({ username: '', password: '' })

/** 注册表单数据 */
const registerForm = reactive({ username: '', password: '', confirmPassword: '' })

// ── 路由变化时同步 defaultTab ─────────────────────────────────

watch(
  () => props.defaultTab,
  (val) => { activeTab.value = val },
)

// ── 工具方法 ──────────────────────────────────────────────────

/** 设置操作反馈并自动在 5 秒后清除 */
function setFeedback(type, message) {
  feedback.type = type
  feedback.message = message
}

/** 清除反馈 */
function clearFeedback() {
  feedback.type = ''
  feedback.message = ''
}

// ── 登录逻辑 ──────────────────────────────────────────────────

/**
 * 处理登录表单提交
 *
 * 流程：
 *   1. 前端校验（用户名 + 密码非空）
 *   2. 调用 auth.login(username, password)
 *   3. store 内部完成：调 API → 存 token + user → 写 localStorage
 *   4. 成功后跳转：优先跳 route.query.redirect，否则跳首页
 *   5. 失败则显示后端返回的错误信息
 */
async function handleLogin() {
  clearFeedback()

  // 前端校验
  if (!loginForm.username.trim()) {
    setFeedback('error', '请输入用户名')
    return
  }
  if (!loginForm.password) {
    setFeedback('error', '请输入密码')
    return
  }
  if (loginForm.password.length < 6) {
    setFeedback('error', '密码长度不能少于 6 位')
    return
  }

  isSubmitting.value = true
  try {
    await auth.login(loginForm.username.trim(), loginForm.password)
    // 登录成功：跳转到 redirect 目标或首页
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch (e) {
    setFeedback('error', e.message || '登录失败，请检查用户名和密码')
  } finally {
    isSubmitting.value = false
  }
}

// ── 注册逻辑 ──────────────────────────────────────────────────

/**
 * 处理注册表单提交
 *
 * 流程：
 *   1. 前端校验（用户名非空、密码长度 >= 6、两次输入一致）
 *   2. 调用 auth.register(username, password)
 *   3. 成功 → 自动切换到登录 tab，预填用户名，显示成功提示
 *   4. 失败 → 显示后端错误信息
 */
async function handleRegister() {
  clearFeedback()

  // 前端校验
  if (!registerForm.username.trim()) {
    setFeedback('error', '请输入用户名')
    return
  }
  if (registerForm.username.trim().length < 3) {
    setFeedback('error', '用户名长度不能少于 3 位')
    return
  }
  if (!registerForm.password) {
    setFeedback('error', '请输入密码')
    return
  }
  if (registerForm.password.length < 6) {
    setFeedback('error', '密码长度不能少于 6 位')
    return
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    setFeedback('error', '两次输入的密码不一致')
    return
  }

  isSubmitting.value = true
  try {
    await auth.register(registerForm.username.trim(), registerForm.password)
    // 注册成功：预填登录表单并切换到登录 tab
    loginForm.username = registerForm.username.trim()
    loginForm.password = ''
    // 清空注册表单
    registerForm.username = ''
    registerForm.password = ''
    registerForm.confirmPassword = ''
    activeTab.value = 'login'
    setFeedback('success', '注册成功，请登录')
  } catch (e) {
    setFeedback('error', e.message || '注册失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="auth-layout">
    <div class="auth-card">
      <!-- ── 标题 ──────────────────────────────────────────── -->
      <h1>{{ activeTab === 'login' ? '登录' : '注册' }}</h1>
      <p class="subtitle">
        {{ activeTab === 'login' ? '欢迎回来，请登录你的账号' : '创建一个新账号加入论坛' }}
      </p>

      <!-- ── Tab 切换器 ───────────────────────────────────── -->
      <div class="tab-switcher">
        <button
          class="tab-button"
          :class="{ active: activeTab === 'login' }"
          @click="activeTab = 'login'"
        >
          登录
        </button>
        <button
          class="tab-button"
          :class="{ active: activeTab === 'register' }"
          @click="activeTab = 'register'"
        >
          注册
        </button>
      </div>

      <!-- ── 操作反馈 ─────────────────────────────────────── -->
      <div
        v-if="feedback.message"
        class="feedback"
        :class="feedback.type"
      >
        {{ feedback.message }}
      </div>

      <!-- ── 登录表单 ─────────────────────────────────────── -->
      <form
        v-if="activeTab === 'login'"
        class="auth-form"
        @submit.prevent="handleLogin"
      >
        <label>
          用户名
          <input
            v-model.trim="loginForm.username"
            type="text"
            autocomplete="username"
            minlength="3"
            maxlength="50"
            placeholder="请输入用户名"
            required
          >
        </label>
        <label>
          密码
          <input
            v-model="loginForm.password"
            type="password"
            autocomplete="current-password"
            minlength="6"
            maxlength="50"
            placeholder="请输入密码（至少 6 位）"
            required
          >
        </label>
        <button
          type="submit"
          class="submit-button"
          :disabled="isSubmitting"
        >
          {{ isSubmitting ? '登录中...' : '登录' }}
        </button>
      </form>

      <!-- ── 注册表单 ─────────────────────────────────────── -->
      <form
        v-else
        class="auth-form"
        @submit.prevent="handleRegister"
      >
        <label>
          用户名
          <input
            v-model.trim="registerForm.username"
            type="text"
            autocomplete="username"
            minlength="3"
            maxlength="50"
            placeholder="请输入用户名（至少 3 位）"
            required
          >
        </label>
        <label>
          密码
          <input
            v-model="registerForm.password"
            type="password"
            autocomplete="new-password"
            minlength="6"
            maxlength="50"
            placeholder="请输入密码（至少 6 位）"
            required
          >
        </label>
        <label>
          确认密码
          <input
            v-model="registerForm.confirmPassword"
            type="password"
            autocomplete="new-password"
            minlength="6"
            maxlength="50"
            placeholder="请再次输入密码"
            required
          >
        </label>
        <button
          type="submit"
          class="submit-button"
          :disabled="isSubmitting"
        >
          {{ isSubmitting ? '注册中...' : '注册' }}
        </button>
      </form>
    </div>
  </section>
</template>

<style scoped>
/* AuthView 复用 main.css 中定义的全局类（.auth-layout, .auth-card, .tab-switcher, etc.）
   此处仅补充组件独有的微调样式 */
</style>