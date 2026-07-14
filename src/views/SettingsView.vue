<script setup>
/**
 * =============================================================================
 *  SettingsView.vue —— 用户设置页面
 * =============================================================================
 *
 * Django 对比：Django 的 UserChangeForm / PasswordChangeForm / ProfileUpdateView
 *   后端 Django 中，用户设置通常拆分为多个表单：
 *     - UserChangeForm 修改 username、email、bio 等基础字段
 *     - PasswordChangeForm 修改密码（需验证旧密码）
 *     - 头像上传通过单独的视图处理
 *   这里前端用一个页面 + 四个 Tab 统一管理这些操作。
 *
 * 路由：/settings → name: 'settings'（requiresAuth: true）
 *   未登录用户会被全局路由守卫重定向到登录页。
 *
 * 功能：
 *   1. 「个人资料」tab：修改用户名、bio → 调用 updateProfile API
 *   2. 「头像」tab：选择图片文件 → 本地预览 → 调用 uploadAvatar API 上传
 *   3. 「修改密码」tab：旧密码 + 新密码 + 确认密码 → 调用 changePassword API
 *   4. 「危险区域」tab：删除账户（需二次确认） → 调用 DELETE /user/me
 *   5. 每个操作都有 loading 状态、成功/错误反馈（3 秒后自动消失）
 *   6. 操作成功后同步更新 Pinia auth store（updateProfileLocal）
 *   7. 删除账户成功后清除登录状态并跳转到首页
 */

import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import { request } from '@/api/client'
import { getImageUrl } from '@/utils/helpers'

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const auth = useAuthStore()

// ── Tab 状态 ──────────────────────────────────────────────────

/** 当前激活的 tab */
const activeTab = ref('profile') // 'profile' | 'avatar' | 'password' | 'danger'

/** 反馈消息（自动 3 秒后清除） */
const feedback = reactive({ type: '', message: '' })

/** 全局提交锁（任一 tab 操作进行中时为 true） */
const isSubmitting = ref(false)

// ── 个人资料表单 ──────────────────────────────────────────────

/** 资料表单数据，初始值从 auth store 读取 */
const profileForm = reactive({
  username: auth.user?.username || '',
  bio: auth.user?.bio || '',
})

// ── 头像 ──────────────────────────────────────────────────────

/** 用户选择的头像文件（File 对象） */
const avatarFile = ref(null)

/** 本地预览 URL（通过 URL.createObjectURL 生成） */
const avatarPreview = ref('')

// ── 修改密码表单 ──────────────────────────────────────────────

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

// ── 删除账户 ──────────────────────────────────────────────────

/** 是否显示删除确认对话框 */
const showDeleteConfirm = ref(false)

/** 删除确认输入框的值（用户需输入用户名确认） */
const deleteConfirmText = ref('')

// ── 工具函数 ──────────────────────────────────────────────────

/**
 * 设置反馈消息，3 秒后自动清除
 * @param {'success'|'error'} type
 * @param {string} msg
 */
function setFeedback(type, msg) {
  feedback.type = type
  feedback.message = msg
  setTimeout(() => {
    feedback.type = ''
    feedback.message = ''
  }, 3000)
}

// ── Tab 切换 ──────────────────────────────────────────────────

/** 切换 tab 时清除旧的反馈消息 */
function switchTab(tab) {
  activeTab.value = tab
  feedback.type = ''
  feedback.message = ''
}

// ── 个人资料操作 ──────────────────────────────────────────────

/**
 * 保存个人资料
 * 调用 PUT /user/me → 更新 Pinia store → 显示成功反馈
 */
async function handleUpdateProfile() {
  isSubmitting.value = true
  try {
    const data = await authApi.updateProfile({
      username: profileForm.username,
      bio: profileForm.bio,
    })
    // 同步更新 Pinia store 中的用户对象
    auth.updateProfileLocal(data.user || data)
    setFeedback('success', '个人资料已更新')
  } catch (e) {
    setFeedback('error', e.message || '更新失败')
  } finally {
    isSubmitting.value = false
  }
}

// ── 头像操作 ──────────────────────────────────────────────────

/**
 * 用户选择头像文件时触发
 * 生成本地预览 URL，暂不调用 API
 */
function onAvatarChange(e) {
  const file = e.target.files[0]
  if (!file) return
  // 仅允许图片类型
  if (!file.type.startsWith('image/')) {
    setFeedback('error', '请选择图片文件')
    return
  }
  avatarFile.value = file
  // 释放旧的预览 URL
  if (avatarPreview.value && avatarPreview.value.startsWith('blob:')) {
    URL.revokeObjectURL(avatarPreview.value)
  }
  avatarPreview.value = URL.createObjectURL(file)
}

/**
 * 上传头像
 * 调用 POST /user/me/avatar → 更新 store → 清除本地预览
 */
async function handleUploadAvatar() {
  if (!avatarFile.value) return
  isSubmitting.value = true
  try {
    const data = await authApi.uploadAvatar(avatarFile.value)
    auth.updateProfileLocal(data.user || data)
    setFeedback('success', '头像已更新')
    // 清除本地选择状态
    avatarFile.value = null
    if (avatarPreview.value.startsWith('blob:')) {
      URL.revokeObjectURL(avatarPreview.value)
    }
    avatarPreview.value = ''
    // 重置 file input（通过 key 强制重新渲染）
  } catch (e) {
    setFeedback('error', e.message || '上传失败')
  } finally {
    isSubmitting.value = false
  }
}

// ── 修改密码操作 ──────────────────────────────────────────────

/**
 * 修改密码
 * 验证两次输入一致 → 调用 PUT /user/me/password
 */
async function handleChangePassword() {
  // 前端校验
  if (!passwordForm.old_password) {
    setFeedback('error', '请输入旧密码')
    return
  }
  if (!passwordForm.new_password || passwordForm.new_password.length < 6) {
    setFeedback('error', '新密码至少 6 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    setFeedback('error', '两次输入的新密码不一致')
    return
  }

  isSubmitting.value = true
  try {
    await authApi.changePassword(
      passwordForm.old_password,
      passwordForm.new_password,
    )
    setFeedback('success', '密码已修改，请牢记新密码')
    // 清空表单
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch (e) {
    setFeedback('error', e.message || '密码修改失败')
  } finally {
    isSubmitting.value = false
  }
}

// ── 删除账户操作 ──────────────────────────────────────────────

/** 打开删除确认对话框 */
function openDeleteConfirm() {
  deleteConfirmText.value = ''
  showDeleteConfirm.value = true
}

/** 关闭删除确认对话框 */
function cancelDelete() {
  showDeleteConfirm.value = false
  deleteConfirmText.value = ''
}

/**
 * 确认删除账户
 * 先验证用户输入的确认文本与用户名一致
 * → 调用 DELETE /user/me → 清除登录状态 → 跳转首页
 */
async function handleDeleteAccount() {
  const expectedName = auth.user?.username || ''
  if (deleteConfirmText.value !== expectedName) {
    setFeedback('error', `请输入你的用户名 "${expectedName}" 以确认删除`)
    return
  }

  isSubmitting.value = true
  try {
    await request('/user/me', { method: 'DELETE' })
    // 清除 store 的登录状态
    auth.logout()
    // 重置 UI 状态
    showDeleteConfirm.value = false
    deleteConfirmText.value = ''
    // 跳转到首页并显示简短的提示（通过 query 参数）
    router.push({ name: 'home', query: { deleted: '1' } })
  } catch (e) {
    setFeedback('error', e.message || '删除账户失败')
    showDeleteConfirm.value = false
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="forum-container">
    <h2 class="settings-title">设置</h2>

    <!-- ════ Tab 切换栏 ════════════════════════════════════ -->
    <div class="tab-switcher settings-tabs">
      <button
        class="tab-button"
        :class="{ active: activeTab === 'profile' }"
        @click="switchTab('profile')"
      >
        个人资料
      </button>
      <button
        class="tab-button"
        :class="{ active: activeTab === 'avatar' }"
        @click="switchTab('avatar')"
      >
        头像
      </button>
      <button
        class="tab-button"
        :class="{ active: activeTab === 'password' }"
        @click="switchTab('password')"
      >
        修改密码
      </button>
      <button
        class="tab-button danger-tab"
        :class="{ active: activeTab === 'danger' }"
        @click="switchTab('danger')"
      >
        危险区域
      </button>
    </div>

    <!-- ════ 全局反馈消息 ═══════════════════════════════════ -->
    <div
      v-if="feedback.message"
      class="feedback"
      :class="feedback.type"
    >
      {{ feedback.message }}
    </div>

    <!-- ════════════════════════════════════════════════════════ -->
    <!-- Tab 1: 个人资料                                         -->
    <!-- ════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'profile'" class="settings-form">
      <label>
        用户名
        <input
          v-model.trim="profileForm.username"
          type="text"
          minlength="3"
          maxlength="50"
          placeholder="输入用户名"
        />
      </label>
      <label>
        个人简介
        <textarea
          v-model="profileForm.bio"
          maxlength="500"
          rows="4"
          placeholder="介绍一下自己，让其他人更了解你..."
        />
      </label>
      <div class="form-actions">
        <button
          class="btn-primary"
          :disabled="isSubmitting"
          @click="handleUpdateProfile"
        >
          {{ isSubmitting ? '保存中...' : '保存修改' }}
        </button>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════ -->
    <!-- Tab 2: 头像                                             -->
    <!-- ════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'avatar'" class="settings-form">
      <div class="avatar-section">
        <!-- 当前头像 / 本地预览 -->
        <div class="avatar-display">
          <img
            v-if="avatarPreview"
            :src="avatarPreview"
            alt="头像预览"
            class="current-avatar"
          />
          <img
            v-else-if="auth.user?.avatar_url"
            :src="getImageUrl(auth.user.avatar_url)"
            alt="当前头像"
            class="current-avatar"
          />
          <div v-else class="current-avatar placeholder">
            {{ auth.user?.username?.[0]?.toUpperCase() }}
          </div>
        </div>

        <!-- 文件选择器（每次选择后通过 key 重置 input） -->
        <div class="avatar-upload-row">
          <label class="file-select-label">
            选择图片
            <input
              type="file"
              accept="image/*"
              class="file-input-hidden"
              @change="onAvatarChange"
            />
          </label>
          <span v-if="avatarFile" class="file-name">{{ avatarFile.name }}</span>
        </div>

        <button
          class="btn-primary"
          :disabled="!avatarFile || isSubmitting"
          @click="handleUploadAvatar"
        >
          {{ isSubmitting ? '上传中...' : '上传新头像' }}
        </button>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════ -->
    <!-- Tab 3: 修改密码                                         -->
    <!-- ════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'password'" class="settings-form">
      <label>
        旧密码
        <input
          v-model="passwordForm.old_password"
          type="password"
          autocomplete="current-password"
          placeholder="输入当前密码"
        />
      </label>
      <label>
        新密码
        <input
          v-model="passwordForm.new_password"
          type="password"
          minlength="6"
          maxlength="50"
          autocomplete="new-password"
          placeholder="至少 6 位"
        />
      </label>
      <label>
        确认新密码
        <input
          v-model="passwordForm.confirm_password"
          type="password"
          minlength="6"
          maxlength="50"
          autocomplete="new-password"
          placeholder="再次输入新密码"
        />
      </label>
      <div class="form-actions">
        <button
          class="btn-primary"
          :disabled="isSubmitting"
          @click="handleChangePassword"
        >
          {{ isSubmitting ? '修改中...' : '修改密码' }}
        </button>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════ -->
    <!-- Tab 4: 危险区域                                         -->
    <!-- ════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'danger'" class="settings-form">
      <div class="danger-zone">
        <div class="danger-header">
          <h3>删除账户</h3>
          <p>此操作不可撤销。你的所有帖子、评论、收藏和数据将被永久删除。</p>
        </div>

        <!-- 未确认时显示删除按钮 -->
        <div v-if="!showDeleteConfirm">
          <button
            class="btn-danger-large"
            @click="openDeleteConfirm"
          >
            删除我的账户
          </button>
        </div>

        <!-- 确认对话框 -->
        <div v-else class="delete-confirm-box">
          <p class="confirm-warning">
            请输入你的用户名 <strong>{{ auth.user?.username }}</strong> 以确认删除：
          </p>
          <input
            v-model="deleteConfirmText"
            type="text"
            class="confirm-input"
            placeholder="输入用户名确认"
            @keyup.enter="handleDeleteAccount"
          />
          <div class="confirm-actions">
            <button
              class="btn-danger-large"
              :disabled="deleteConfirmText !== auth.user?.username || isSubmitting"
              @click="handleDeleteAccount"
            >
              {{ isSubmitting ? '删除中...' : '确认删除' }}
            </button>
            <button
              class="btn-secondary"
              :disabled="isSubmitting"
              @click="cancelDelete"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ── 页面标题 ──────────────────────────────────────────────── */

.settings-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0 0 24px;
  color: var(--color-text);
  letter-spacing: -0.03em;
}

/* ── Tab 切换栏 ────────────────────────────────────────────── */

.settings-tabs {
  grid-template-columns: repeat(4, 1fr);
  margin-bottom: 24px;
}

/* 危险区域 tab 按钮的红色 hover 样式 */
.danger-tab:hover {
  color: var(--color-danger);
}

.danger-tab.active {
  color: var(--color-danger);
}

/* ── 反馈消息 ──────────────────────────────────────────────── */

.feedback {
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 0.88rem;
  margin-bottom: 16px;
}

.feedback.success {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
}

.feedback.error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
}

/* ── 表单通用样式 ──────────────────────────────────────────── */

.settings-form {
  display: grid;
  gap: 18px;
  max-width: 520px;
}

.settings-form label {
  display: grid;
  gap: 6px;
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--color-text);
}

.settings-form input[type="text"],
.settings-form input[type="password"],
.settings-form textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.95rem;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.settings-form input:focus,
.settings-form textarea:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.settings-form textarea {
  resize: vertical;
  min-height: 90px;
  line-height: 1.5;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ── 头像区域 ──────────────────────────────────────────────── */

.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 10px 0;
}

.avatar-display {
  display: flex;
  align-items: center;
  justify-content: center;
}

.current-avatar {
  width: 128px;
  height: 128px;
  border-radius: 50%;
  object-fit: cover;
  border: 3px solid var(--color-border);
  box-shadow: var(--shadow);
}

.current-avatar.placeholder {
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3rem;
  font-weight: 700;
  border-color: var(--color-accent);
}

.avatar-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.file-select-label {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 8px 18px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
  display: inline-block;
}

.file-select-label:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.file-input-hidden {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.file-name {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 危险区域 ──────────────────────────────────────────────── */

.danger-zone {
  border: 2px solid #fecaca;
  border-radius: var(--radius);
  padding: 28px;
  background: #fff5f5;
}

.danger-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--color-danger);
}

.danger-header p {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
  margin: 0 0 22px;
  line-height: 1.6;
}

.btn-danger-large {
  border: 0;
  border-radius: 10px;
  padding: 11px 24px;
  background: var(--color-danger);
  color: #fff;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-danger-large:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.btn-danger-large:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 删除确认框 */
.delete-confirm-box {
  margin-top: 8px;
}

.confirm-warning {
  font-size: 0.92rem;
  color: var(--color-text);
  margin: 0 0 14px;
  line-height: 1.5;
}

.confirm-warning strong {
  color: var(--color-danger);
  font-weight: 600;
}

.confirm-input {
  width: 100%;
  padding: 10px 14px;
  border: 2px solid #fca5a5;
  border-radius: 10px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.95rem;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  margin-bottom: 16px;
}

.confirm-input:focus {
  border-color: var(--color-danger);
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.15);
}

.confirm-actions {
  display: flex;
  gap: 10px;
}

/* ── 响应式 ────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .settings-tabs {
    grid-template-columns: repeat(2, 1fr);
  }

  .settings-form {
    max-width: 100%;
  }

  .danger-zone {
    padding: 20px;
  }

  .confirm-actions {
    flex-direction: column;
  }
}
</style>