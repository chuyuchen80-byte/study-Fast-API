<script setup>
/**
 * =============================================================================
 *  CreatePostView.vue —— 发布/编辑帖子页面（v2.0 全功能版）
 * =============================================================================
 *
 * Django 对比：Django 的 CreateView / UpdateView
 *
 * 路由：
 *   /create    → name: 'create-post'（meta.requiresAuth: true）
 *   /edit/:id  → name: 'edit-post'  （meta.requiresAuth: true, props: true）
 *
 * 功能：
 *   1. 无 id prop → 创建模式；有 id prop → 编辑模式（预填现有数据）
 *   2. 标题输入（max 100 字）
 *   3. 正文 textarea（Markdown 编辑 + 实时预览 tab 切换）
 *   4. 分类下拉框（fetch categories API）
 *   5. 标签输入（逗号分隔，带 autocomplete 下拉建议，从 getTags API 获取）
 *   6. ImageUploader 组件（上传图片）
 *   7. 提交：创建 → postsApi.createPost()，编辑 → postsApi.updatePost()
 *   8. 取消：返回到 /forum 或帖子详情页
 *   9. 表单校验：标题必填、内容必填
 *   10. 加载/错误/提交中状态
 */
import { onMounted, reactive, ref, watch, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as postsApi from '@/api/posts'
import * as categoriesApi from '@/api/categories'
import { renderMarkdown } from '@/utils/markdown'
import ImageUploader from '@/components/ImageUploader.vue'

// ── Props（由路由注入）─────────────────────────────────────────

const props = defineProps({
  /** 帖子 ID（编辑模式时由路由 :id 传入，创建模式为 undefined/null） */
  id: {
    type: [String, Number],
    default: null,
  },
})

// ── 全局依赖 ──────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ── 模式判断 ──────────────────────────────────────────────────

/** 是否为编辑模式 */
const isEditMode = computed(() => !!props.id)

/** 页面标题 */
const pageTitle = computed(() => isEditMode.value ? '编辑帖子' : '发布新帖')

// ── 表单状态 ──────────────────────────────────────────────────

/** 帖子标题 */
const title = ref('')

/** 帖子正文（Markdown 原始文本） */
const content = ref('')

/** 选中的分类 ID */
const categoryId = ref(null)

/** 标签输入框原始文本（逗号分隔） */
const tagsInput = ref('')

/** 上传的图片文件列表 */
const uploadedFiles = ref([])

// ── 分类列表 ──────────────────────────────────────────────────

const categories = ref([])

// ── 标签建议 ──────────────────────────────────────────────────

/** 标签自动完成建议列表 */
const tagSuggestions = ref([])

/** 是否显示标签建议下拉 */
const showTagSuggestions = ref(false)

/** 建议加载中 */
const tagSuggestionsLoading = ref(false)

/** 标签搜索防抖定时器 */
let tagDebounceTimer = null

// ── 内容编辑模式 ──────────────────────────────────────────────

/** 当前激活的内容 tab：'edit' | 'preview' */
const contentTab = ref('edit')

/** 生成的 Markdown 预览 HTML */
const previewHtml = computed(() => {
  if (!content.value) return '<p style="color: var(--color-text-secondary)">暂无内容</p>'
  return renderMarkdown(content.value)
})

// ── 提交状态 ──────────────────────────────────────────────────

/** 是否正在提交 */
const isSubmitting = ref(false)

/** 错误/成功消息 */
const feedback = reactive({ type: '', message: '' })

// ── 标签解析 ──────────────────────────────────────────────────

/**
 * 从逗号分隔的输入字符串解析标签数组
 * 去除前后空格，过滤空字符串
 */
function parseTags() {
  return tagsInput.value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

/**
 * 将标签数组还原为逗号分隔的字符串（编辑模式预填用）
 */
function tagsToString(tags) {
  if (!tags || !Array.isArray(tags)) return ''
  return tags.map((t) => (typeof t === 'string' ? t : t.name || '')).filter(Boolean).join(', ')
}

// ── 标签自动完成 ──────────────────────────────────────────────

/**
 * 当标签输入框值变化时，搜索匹配的标签建议（300ms 防抖）
 *
 * 触发条件：
 *   用户输入了逗号之后的空白区域（即正在输入新标签）
 *   → 取最后一个逗号之后的片段作为搜索词
 */
function onTagsInput(e) {
  // 触发建议搜索
  const val = e.target.value
  if (tagDebounceTimer) clearTimeout(tagDebounceTimer)

  tagDebounceTimer = setTimeout(async () => {
    // 取最后一段（正在输入的标签名）
    const parts = val.split(',')
    const lastPart = parts[parts.length - 1].trim()
    if (!lastPart || lastPart.length < 1) {
      tagSuggestions.value = []
      showTagSuggestions.value = false
      return
    }

    tagSuggestionsLoading.value = true
    try {
      const tags = await categoriesApi.getTags(lastPart)
      // 排除已在输入框中的标签
      const existing = new Set(parts.slice(0, -1).map((s) => s.trim()).filter(Boolean))
      tagSuggestions.value = (Array.isArray(tags) ? tags : []).filter(
        (t) => !existing.has(t.name)
      )
      showTagSuggestions.value = tagSuggestions.value.length > 0
    } catch {
      tagSuggestions.value = []
      showTagSuggestions.value = false
    } finally {
      tagSuggestionsLoading.value = false
    }
  }, 300)
}

/** 选择建议标签：替换输入框最后一段 */
function selectTagSuggestion(tagName) {
  const parts = tagsInput.value.split(',')
  parts[parts.length - 1] = ` ${tagName}`
  tagsInput.value = parts.join(',').replace(/^,/, '').trim()
  showTagSuggestions.value = false

  // focus back to input
  nextTick(() => {
    const el = document.querySelector('.tags-input')
    if (el) el.focus()
  })
}

/** 失焦时延迟隐藏建议（给点击选择留时间） */
function onTagsBlur() {
  setTimeout(() => {
    showTagSuggestions.value = false
  }, 200)
}

// ── 表单校验 ──────────────────────────────────────────────────

function validate() {
  if (!title.value.trim()) return '请输入帖子标题'
  if (title.value.trim().length > 100) return '标题不能超过 100 个字符'
  if (!content.value.trim()) return '请输入帖子内容'
  return null
}

// ── 分类数据加载 ──────────────────────────────────────────────

async function fetchCategories() {
  try {
    categories.value = await categoriesApi.getCategories()
  } catch {
    // 分类加载失败不阻塞表单
  }
}

// ── 编辑模式：预填表单 ────────────────────────────────────────

async function loadPostForEdit() {
  const postId = Number(props.id)
  if (!postId || Number.isNaN(postId)) return

  try {
    const data = await postsApi.getPost(postId)
    title.value = data.title || ''
    content.value = data.content || ''
    categoryId.value = data.category?.id || null
    tagsInput.value = tagsToString(data.tags || [])
  } catch (e) {
    setFeedback('error', e.message || '加载帖子失败')
  }
}

// ── 提交逻辑 ──────────────────────────────────────────────────

/**
 * 提交表单（创建 或 更新）
 *
 * 创建：调用 postsApi.createPost({ title, content, category_id, tags, files })
 * 更新：调用 postsApi.updatePost(postId, { title, content, category_id, tags })
 */
async function handleSubmit() {
  const validationError = validate()
  if (validationError) {
    setFeedback('error', validationError)
    return
  }

  isSubmitting.value = true
  clearFeedback()

  // 公共字段
  const payload = {
    title: title.value.trim(),
    content: content.value.trim(),
    ...(categoryId.value ? { category_id: categoryId.value } : {}),
    ...(tagsInput.value.trim() ? { tags: tagsInput.value.trim() } : {}),
  }

  try {
    if (isEditMode.value) {
      await postsApi.updatePost(Number(props.id), payload)
      setFeedback('success', '帖子已更新')
      // 跳回详情页
      router.push({ name: 'post-detail', params: { id: props.id } })
    } else {
      // 创建模式支持图片上传
      const result = await postsApi.createPost({
        ...payload,
        files: uploadedFiles.value,
      })
      setFeedback('success', '帖子发布成功')
      // 跳转到新帖详情（后端返回的 result 中包含 id）
      const newId = result.id || result.post?.id
      if (newId) {
        router.push({ name: 'post-detail', params: { id: newId } })
      } else {
        router.push({ name: 'forum' })
      }
    }
  } catch (e) {
    setFeedback('error', e.message || '提交失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

/** 取消：返回上一页或论坛 */
function handleCancel() {
  if (isEditMode.value) {
    router.push({ name: 'post-detail', params: { id: props.id } })
  } else {
    router.push({ name: 'forum' })
  }
}

// ── 工具方法 ──────────────────────────────────────────────────

function setFeedback(type, message) {
  feedback.type = type
  feedback.message = message
}

function clearFeedback() {
  feedback.type = ''
  feedback.message = ''
}

// ── 生命周期 ──────────────────────────────────────────────────

onMounted(async () => {
  await fetchCategories()

  if (isEditMode.value) {
    await loadPostForEdit()
  }
})
</script>

<template>
  <div class="forum-container">
    <!-- ── 返回按钮 ─────────────────────────────────────────── -->
    <button class="btn-back" @click="handleCancel">&larr; 返回</button>

    <!-- ── 页面标题 ────────────────────────────────────────── -->
    <h2 class="page-title">{{ pageTitle }}</h2>

    <!-- ── 操作反馈 ───────────────────────────────────────── -->
    <div v-if="feedback.message" class="feedback" :class="feedback.type">
      {{ feedback.message }}
    </div>

    <!-- ── 帖子表单 ───────────────────────────────────────── -->
    <form class="create-post-form" @submit.prevent="handleSubmit">
      <!-- 标题 -->
      <label>
        标题
        <input
          v-model="title"
          type="text"
          maxlength="100"
          placeholder="请输入帖子标题（最多 100 字）"
          required
        >
        <span class="char-count">{{ title.length }} / 100</span>
      </label>

      <!-- 分类下拉 -->
      <label>
        分类
        <select v-model.number="categoryId">
          <option :value="null">无分类</option>
          <option
            v-for="cat in categories"
            :key="cat.id"
            :value="cat.id"
          >
            {{ cat.name }}
          </option>
        </select>
      </label>

      <!-- 标签输入（逗号分隔 + 自动完成） -->
      <label class="tags-label">
        标签
        <span class="label-hint">（用逗号分隔多个标签）</span>
        <div class="tags-wrapper">
          <input
            v-model="tagsInput"
            type="text"
            class="tags-input"
            placeholder="例如：技术, Python, 新手教程"
            autocomplete="off"
            @input="onTagsInput"
            @blur="onTagsBlur"
            @focus="onTagsInput({ target: { value: tagsInput } })"
          >
          <!-- 标签建议下拉 -->
          <div v-if="showTagSuggestions" class="tags-suggestions">
            <div v-if="tagSuggestionsLoading" class="suggestion-loading">
              搜索中...
            </div>
            <button
              v-for="sug in tagSuggestions"
              :key="sug.id || sug.name"
              type="button"
              class="suggestion-item"
              @mousedown.prevent="selectTagSuggestion(sug.name)"
            >
              #{{ sug.name }}
            </button>
          </div>
        </div>
      </label>

      <!-- 正文编辑区（编辑 / 预览 Tab 切换） -->
      <label class="content-label">
        正文
        <span class="label-hint">（支持 Markdown 格式）</span>

        <!-- Tab 切换 -->
        <div class="content-tabs">
          <button
            type="button"
            class="content-tab"
            :class="{ active: contentTab === 'edit' }"
            @click="contentTab = 'edit'"
          >
            编辑
          </button>
          <button
            type="button"
            class="content-tab"
            :class="{ active: contentTab === 'preview' }"
            @click="contentTab = 'preview'"
          >
            预览
          </button>
        </div>

        <!-- 编辑模式 -->
        <textarea
          v-if="contentTab === 'edit'"
          v-model="content"
          class="content-textarea"
          placeholder="输入帖子内容...（支持 Markdown）"
          rows="12"
          required
        />

        <!-- 预览模式 -->
        <div
          v-else
          class="content-preview"
          v-html="previewHtml"
        />
      </label>

      <!-- 图片上传组件（仅创建模式，编辑模式不显示） -->
      <label v-if="!isEditMode">
        图片（可选）
        <ImageUploader v-model="uploadedFiles" :max-files="9" :max-size="5" />
      </label>

      <!-- 提交 / 取消按钮 -->
      <div class="form-actions">
        <button
          type="button"
          class="btn-secondary"
          @click="handleCancel"
        >
          取消
        </button>
        <button
          type="submit"
          class="btn-primary"
          :disabled="isSubmitting"
        >
          {{ isSubmitting ? '提交中...' : (isEditMode ? '更新帖子' : '发布帖子') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
/* ── 全局类由 main.css 提供：.forum-container, .create-post-form, .btn-back, .btn-primary, .btn-secondary 等 ── */

.page-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin: 0 0 24px;
  color: var(--color-text);
  letter-spacing: -0.03em;
}

/* ── 表单增强 ────────────────────────────────────────────────── */

.create-post-form label {
  display: grid;
  gap: 6px;
  color: var(--color-text);
  font-weight: 500;
  font-size: 0.9rem;
}

.create-post-form input[type="text"],
.create-post-form textarea,
.create-post-form select {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg);
  padding: 11px 14px;
  color: var(--color-text);
  outline: none;
  font-size: 0.95rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.create-post-form input[type="text"]:focus,
.create-post-form textarea:focus,
.create-post-form select:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.create-post-form select {
  cursor: pointer;
  appearance: auto;
}

.char-count {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  text-align: right;
  font-weight: 400;
}

/* ── 标签输入 ────────────────────────────────────────────────── */

.tags-label {
  position: relative;
}

.label-hint {
  font-weight: 400;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.tags-wrapper {
  position: relative;
}

.tags-input {
  width: 100%;
}

/* ── 标签建议下拉 ──────────────────────────────────────────── */

.tags-suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 50;
  max-height: 200px;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: var(--shadow-md);
  margin-top: 4px;
}

.suggestion-loading {
  padding: 10px 14px;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
}

.suggestion-item {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 10px 14px;
  color: var(--color-text);
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.1s ease;
}

.suggestion-item:hover {
  background: var(--color-accent);
  color: #fff;
}

.suggestion-item:not(:last-child) {
  border-bottom: 1px solid var(--color-border);
}

/* ── 正文 Tab 切换 ──────────────────────────────────────────── */

.content-label {
  display: grid !important;
  gap: 8px;
}

.content-tabs {
  display: flex;
  gap: 4px;
  background: #f3f4f6;
  border-radius: 8px;
  padding: 3px;
}

.content-tab {
  flex: 1;
  border: 0;
  border-radius: 6px;
  padding: 8px 16px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.content-tab.active {
  background: var(--color-surface);
  color: var(--color-text);
  box-shadow: var(--shadow);
}

/* ── 正文编辑框 ──────────────────────────────────────────────── */

.content-textarea {
  resize: vertical;
  min-height: 240px;
  font-family:
    'Cascadia Code', 'Fira Code', 'JetBrains Mono',
    'Courier New', monospace;
  font-size: 0.93rem !important;
  line-height: 1.7;
}

/* ── Markdown 预览区 ────────────────────────────────────────── */

.content-preview {
  min-height: 240px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
  padding: 16px 18px;
  color: var(--color-text);
  font-size: 0.95rem;
  line-height: 1.85;
  word-break: break-word;
  overflow-y: auto;
  max-height: 600px;
}

/* Markdown 渲染后的内部元素样式 */
.content-preview :deep(h1),
.content-preview :deep(h2),
.content-preview :deep(h3) {
  margin: 1em 0 0.5em;
  font-weight: 600;
}

.content-preview :deep(h1) { font-size: 1.4rem; }
.content-preview :deep(h2) { font-size: 1.15rem; }
.content-preview :deep(h3) { font-size: 1.05rem; }

.content-preview :deep(p) {
  margin: 0 0 0.8em;
}

.content-preview :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.content-preview :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.88em;
  margin: 0.8em 0;
}

.content-preview :deep(pre code) {
  background: transparent;
  padding: 0;
}

.content-preview :deep(blockquote) {
  border-left: 4px solid var(--color-border);
  padding-left: 14px;
  margin: 0.8em 0;
  color: var(--color-text-secondary);
}

.content-preview :deep(a) {
  color: var(--color-accent);
}

.content-preview :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

.content-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
}

.content-preview :deep(th),
.content-preview :deep(td) {
  border: 1px solid var(--color-border);
  padding: 8px 12px;
  text-align: left;
}

.content-preview :deep(th) {
  background: #f3f4f6;
  font-weight: 600;
}

/* ── 反馈 ────────────────────────────────────────────────────── */

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

/* ── 表单操作行 ──────────────────────────────────────────────── */

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}

/* ── 响应式 ──────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .form-actions {
    flex-direction: column;
  }

  .content-preview {
    max-height: 400px;
  }
}
</style>