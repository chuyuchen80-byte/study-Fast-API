<script setup>
/**
 * =============================================================================
 *  CommentSection.vue —— 完整评论区组件（含嵌套回复 + 编辑/删除）
 * =============================================================================
 *
 * Django 对比：
 *   Django 模板中通常是一个 comment_list.html include + JS 处理回复展开
 *   这里封装为一个自包含的 Vue 组件，管理完整的评论 CRUD 状态
 *
 * Props:
 *   postId        — 帖子 ID，用于请求评论数据
 *   postAuthorId  — 帖子作者 ID（可选，用于 OP 标记）
 *
 * 功能：
 *   1. 载入评论列表（含 1 层嵌套回复）
 *   2. 发表顶级评论
 *   3. 回复某条评论（嵌套 1 层）
 *   4. 编辑自己发表的评论（内联编辑）
 *   5. 删除自己的评论（作者），管理员可删除任意评论
 *   6. Markdown 渲染评论内容
 *
 * 权限：
 *   - 编辑：仅限评论作者本人
 *   - 删除：评论作者本人 或 管理员
 *   - OP（Original Poster）标记：评论作者是帖子作者时显示
 */

import { onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import * as commentsApi from '@/api/comments'
import { formatDate, getImageUrl } from '@/utils/helpers'
import { renderMarkdown } from '@/utils/markdown'

// ── Props ──────────────────────────────────────────────────

const props = defineProps({
  /** 帖子 ID */
  postId: {
    type: Number,
    required: true,
  },
  /** 帖子作者 ID（用于显示 OP 标记） */
  postAuthorId: {
    type: Number,
    default: null,
  },
})

// ── 全局依赖 ──────────────────────────────────────────────

const auth = useAuthStore()

// ── 核心状态 ──────────────────────────────────────────────

/** 扁平化的评论列表（展开嵌套回复到第一层） */
const comments = ref([])

/** 评论总数（含回复） */
const totalCount = ref(0)

/** 是否正在加载评论 */
const isLoading = ref(false)

/** 错误消息 */
const error = ref('')

// ── 顶级评论表单 ──────────────────────────────────────────

/** 新的顶级评论内容 */
const newComment = ref('')

/** 是否正在提交评论 */
const isSubmitting = ref(false)

// ── 回复表单状态 ──────────────────────────────────────────

/**
 * 当前正在回复的评论信息
 * null 表示未展开任何回复表单
 * { id: number, username: string }
 */
const replyingTo = ref(null)

/** 回复内容 */
const replyContent = ref('')

/** 是否正在提交回复 */
const isReplying = ref(false)

// ── 编辑状态 ──────────────────────────────────────────────

/**
 * 编辑状态映射：commentId -> { editing: boolean, content: string }
 * 使用 reactive 对象使得深层属性变更可以触发视图更新
 */
const editStates = reactive({})

/** 是否正在保存编辑 */
const isEditing = ref(false)

// ── 删除状态 ──────────────────────────────────────────────

/** 正在删除中的评论 ID 集合（每个评论独立的 loading 状态） */
const deletingIds = reactive(new Set())

// ── 数据加载 ──────────────────────────────────────────────

/**
 * 从后端获取评论列表并展开为扁平结构（深度 0 或 1）
 *
 * 后端返回结构示例：
 *   [
 *     { id:1, content:'...', user:{...}, parent_id:null, replies: [
 *         { id:2, content:'...', user:{...}, parent_id:1, replies: [] }
 *     ]},
 *   ]
 *
 * 展开后：
 *   [
 *     { comment: { id:1, ... }, depth: 0 },
 *     { comment: { id:2, ... }, depth: 1 },
 *   ]
 */
async function fetchComments() {
  isLoading.value = true
  error.value = ''
  try {
    const raw = await commentsApi.getComments(props.postId)
    // 后端可能返回数组直接就是评论列表，也可能包在 { comments: [...] } 中
    const list = Array.isArray(raw) ? raw : (raw.comments || [])

    const flat = []
    list.forEach((comment) => {
      // 顶级评论
      flat.push({ comment, depth: 0 })
      // 展开一层回复
      if (comment.replies && comment.replies.length > 0) {
        comment.replies.forEach((reply) => {
          flat.push({ comment: reply, depth: 1 })
        })
      }
    })

    comments.value = flat
    totalCount.value = flat.length
  } catch (e) {
    error.value = e.message || '加载评论失败'
  } finally {
    isLoading.value = false
  }
}

// ── 顶级评论发表 ──────────────────────────────────────────

/** 提交顶级评论 */
async function submitComment() {
  const text = newComment.value.trim()
  if (!text) return

  isSubmitting.value = true
  error.value = ''
  try {
    const created = await commentsApi.addComment(props.postId, text, null)
    // 新评论没有嵌套回复，直接追加到列表尾部
    comments.value.push({ comment: created, depth: 0 })
    totalCount.value = comments.value.length
    newComment.value = ''
  } catch (e) {
    error.value = e.message || '发表评论失败'
  } finally {
    isSubmitting.value = false
  }
}

// ── 回复流程 ──────────────────────────────────────────────

/** 打开回复表单 */
function startReply(comment) {
  replyingTo.value = { id: comment.id, username: comment.user?.username || '匿名' }
  replyContent.value = ''
}

/** 取消回复 */
function cancelReply() {
  replyingTo.value = null
  replyContent.value = ''
}

/** 提交回复 */
async function submitReply() {
  const text = replyContent.value.trim()
  if (!text || !replyingTo.value) return

  isReplying.value = true
  error.value = ''
  try {
    const created = await commentsApi.addComment(
      props.postId,
      text,
      replyingTo.value.id
    )
    // 找到被回复的评论在列表中的位置，将新回复插入其后
    const parentIndex = comments.value.findIndex(
      (item) => item.comment.id === replyingTo.value.id
    )
    if (parentIndex >= 0) {
      comments.value.splice(parentIndex + 1, 0, { comment: created, depth: 1 })
    } else {
      comments.value.push({ comment: created, depth: 1 })
    }
    totalCount.value = comments.value.length
    cancelReply()
  } catch (e) {
    error.value = e.message || '发表回复失败'
  } finally {
    isReplying.value = false
  }
}

// ── 编辑流程 ──────────────────────────────────────────────

/** 进入编辑模式 */
function startEdit(comment) {
  editStates[comment.id] = {
    editing: true,
    content: comment.content,
  }
}

/** 取消编辑 */
function cancelEdit(commentId) {
  delete editStates[commentId]
}

/** 保存编辑 */
async function saveEdit(commentId) {
  const state = editStates[commentId]
  if (!state || !state.content.trim()) return

  isEditing.value = true
  error.value = ''
  try {
    const updated = await commentsApi.updateComment(
      props.postId,
      commentId,
      state.content.trim()
    )
    // 更新列表中的评论数据
    const entry = comments.value.find((item) => item.comment.id === commentId)
    if (entry) {
      entry.comment.content = updated.content || state.content.trim()
      entry.comment.updated_at = updated.updated_at || new Date().toISOString()
    }
    delete editStates[commentId]
  } catch (e) {
    error.value = e.message || '编辑评论失败'
  } finally {
    isEditing.value = false
  }
}

// ── 删除流程 ──────────────────────────────────────────────

/** 删除评论（含确认对话框） */
async function deleteComment(commentId) {
  if (!window.confirm('确定要删除这条评论吗？此操作不可撤销。')) return

  deletingIds.add(commentId)
  error.value = ''
  try {
    await commentsApi.deleteComment(props.postId, commentId)
    // 从列表中移除（同时移除其嵌套回复）
    const index = comments.value.findIndex(
      (item) => item.comment.id === commentId
    )
    if (index >= 0) {
      const entry = comments.value[index]
      if (entry.depth === 0) {
        let end = index + 1
        while (end < comments.value.length && comments.value[end].depth > 0) end++
        comments.value.splice(index, end - index)
      } else {
        comments.value.splice(index, 1)
      }
    }
    totalCount.value = comments.value.length
  } catch (e) {
    error.value = e.message || '删除评论失败'
  } finally {
    deletingIds.delete(commentId)
  }
}

// ── 权限判断 ──────────────────────────────────────────────

/** 当前用户是否有权编辑这条评论（仅作者本人） */
function canEdit(comment) {
  return auth.isLoggedIn && auth.user?.id === comment.user?.id
}

/** 当前用户是否有权删除这条评论（作者本人 或 管理员） */
function canDelete(comment) {
  if (!auth.isLoggedIn) return false
  return auth.user?.id === comment.user?.id || auth.isAdmin
}

/** 评论作者是否为帖子原作者（OP 标记） */
function isOP(comment) {
  return comment.user?.id === props.postAuthorId
}

// ── 生命周期 ──────────────────────────────────────────────

onMounted(() => {
  fetchComments()
})
</script>

<template>
  <section class="comments-section">
    <!-- ── 标题行 ──────────────────────────────────────────── -->
    <h3>评论 ({{ totalCount }})</h3>

    <!-- ── 错误提示 ────────────────────────────────────────── -->
    <div v-if="error" class="feedback error">{{ error }}</div>

    <!-- ── 加载状态 ────────────────────────────────────────── -->
    <div v-if="isLoading" class="loading-state">评论加载中...</div>

    <!-- ── 空状态 ──────────────────────────────────────────── -->
    <div v-else-if="comments.length === 0" class="empty-state">
      <p>暂无评论，来发表第一条评论吧</p>
    </div>

    <!-- ── 评论列表 ────────────────────────────────────────── -->
    <div v-else class="comment-list">
      <div
        v-for="item in comments"
        :key="item.comment.id"
        class="comment-card"
        :class="{ 'comment-reply': item.depth === 1 }"
      >
        <!-- 评论头部 -->
        <div class="comment-header">
          <div class="comment-author">
            <!-- 头像占位 -->
            <span class="comment-avatar">
              {{ (item.comment.user?.username || '?')[0].toUpperCase() }}
            </span>
            <strong>{{ item.comment.user?.username || '匿名用户' }}</strong>
            <!-- OP 标记 -->
            <span v-if="isOP(item.comment)" class="badge badge-op">OP</span>
          </div>
          <span class="comment-time">
            {{ formatDate(item.comment.created_at) }}
            <span
              v-if="item.comment.created_at !== item.comment.updated_at"
              class="comment-edited"
            >
              （已编辑）
            </span>
          </span>
        </div>

        <!-- 评论内容（Markdown 渲染 或 编辑模式） -->
        <div v-if="editStates[item.comment.id]?.editing" class="comment-edit-form">
          <textarea
            v-model="editStates[item.comment.id].content"
            class="edit-textarea"
            rows="3"
            maxlength="2000"
          />
          <div class="edit-actions">
            <button
              class="btn-sm"
              @click="cancelEdit(item.comment.id)"
            >
              取消
            </button>
            <button
              class="btn-primary"
              :style="{ fontSize: '0.82rem', padding: '5px 14px' }"
              :disabled="isEditing || !editStates[item.comment.id]?.content.trim()"
              @click="saveEdit(item.comment.id)"
            >
              {{ isEditing ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>

        <!-- 渲染后的 Markdown 内容 -->
        <div
          v-else
          class="comment-content"
          v-html="renderMarkdown(item.comment.content)"
        />

        <!-- 操作按钮 -->
        <div class="comment-actions">
          <!-- 回复按钮（仅限已登录用户，且不再嵌套超过 1 层） -->
          <button
            v-if="auth.isLoggedIn && item.depth === 0"
            class="btn-comment-action"
            @click="startReply(item.comment)"
          >
            回复
          </button>

          <!-- 编辑按钮（仅作者） -->
          <button
            v-if="canEdit(item.comment) && !editStates[item.comment.id]?.editing"
            class="btn-comment-action"
            @click="startEdit(item.comment)"
          >
            编辑
          </button>

          <!-- 删除按钮（作者或管理员） -->
          <button
            v-if="canDelete(item.comment)"
            class="btn-comment-action btn-comment-danger"
            :disabled="deletingIds.has(item.comment.id)"
            @click="deleteComment(item.comment.id)"
          >
            {{ deletingIds.has(item.comment.id) ? '删除中...' : '删除' }}
          </button>
        </div>

        <!-- ── 内联回复表单 ──────────────────────────── -->
        <div
          v-if="replyingTo?.id === item.comment.id"
          class="reply-form"
        >
          <div class="reply-form-header">
            回复 @{{ replyingTo.username }}：
          </div>
          <textarea
            v-model="replyContent"
            class="reply-textarea"
            placeholder="写下你的回复..."
            rows="3"
            maxlength="2000"
          />
          <div class="reply-form-actions">
            <button class="btn-sm" @click="cancelReply">取消</button>
            <button
              class="btn-primary"
              :style="{ fontSize: '0.82rem', padding: '5px 14px' }"
              :disabled="isReplying || !replyContent.trim()"
              @click="submitReply"
            >
              {{ isReplying ? '发送中...' : '回复' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 顶级评论发布表单 ────────────────────────────────── -->
    <div v-if="auth.isLoggedIn && !isLoading" class="comment-form">
      <textarea
        v-model="newComment"
        placeholder="写下你的评论...（支持 Markdown）"
        rows="3"
        maxlength="2000"
      />
      <button
        class="btn-primary"
        :disabled="isSubmitting || !newComment.trim()"
        @click="submitComment"
      >
        {{ isSubmitting ? '发送中...' : '发表评论' }}
      </button>
    </div>

    <!-- 未登录提示 -->
    <div v-else-if="!isLoading" class="empty-state">
      <p>
        <router-link :to="{ name: 'login', query: { redirect: `/post/${postId}` } }">
          登录
        </router-link>
        后即可发表评论
      </p>
    </div>
  </section>
</template>

<style scoped>
/* ── 使用 main.css 公共类名保证与设计系统一致 ──────────── */

.comments-section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 28px 32px;
  box-shadow: var(--shadow);
}

.comments-section h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 20px;
  color: var(--color-text);
}

/* ── 评论列表 ────────────────────────────────────────────── */

.comment-list {
  display: grid;
  gap: 10px;
  margin-bottom: 22px;
}

.comment-card {
  padding: 16px;
  border-radius: 10px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
}

/* 嵌套回复左缩进 */
.comment-card.comment-reply {
  margin-left: 28px;
  border-left: 3px solid var(--color-accent);
}

.comment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  gap: 8px;
}

.comment-author {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
}

.comment-author strong {
  color: var(--color-text);
  font-size: 0.9rem;
}

.badge-op {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  background: #dbeafe;
  color: #1d4ed8;
}

.comment-time {
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  white-space: nowrap;
}

.comment-edited {
  color: var(--color-text-secondary);
  font-size: 0.72rem;
}

/* ── 评论内容（Markdown 渲染后的 HTML） ────────────────── */

.comment-content {
  color: var(--color-text);
  font-size: 0.93rem;
  line-height: 1.6;
  margin: 0 0 6px;
  word-break: break-word;
}

/* Markdown 渲染后的内部元素样式 */
.comment-content :deep(p) {
  margin: 0 0 8px;
}

.comment-content :deep(p:last-child) {
  margin-bottom: 0;
}

.comment-content :deep(code) {
  background: #e5e7eb;
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 0.88em;
}

.comment-content :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.85em;
  margin: 8px 0;
}

.comment-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.comment-content :deep(blockquote) {
  border-left: 3px solid var(--color-border);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--color-text-secondary);
}

.comment-content :deep(a) {
  color: var(--color-accent);
}

/* ── 操作按钮 ────────────────────────────────────────────── */

.comment-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.btn-comment-action {
  border: 0;
  background: transparent;
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--color-text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-comment-action:hover {
  background: #e5e7eb;
  color: var(--color-text);
}

.btn-comment-danger:hover {
  background: #fee2e2;
  color: var(--color-danger);
}

.btn-comment-action:disabled {
  opacity: 0.5;
  cursor: wait;
}

/* ── 编辑表单 ────────────────────────────────────────────── */

.comment-edit-form {
  display: grid;
  gap: 8px;
  margin-bottom: 6px;
}

.edit-textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  padding: 10px 12px;
  color: var(--color-text);
  outline: none;
  resize: vertical;
  font-size: 0.93rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.edit-textarea:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* ── 回复表单 ────────────────────────────────────────────── */

.reply-form {
  margin-top: 10px;
  padding: 12px;
  background: var(--color-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  display: grid;
  gap: 8px;
}

.reply-form-header {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.reply-textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  padding: 10px 12px;
  color: var(--color-text);
  outline: none;
  resize: vertical;
  font-size: 0.9rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.reply-textarea:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.reply-form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* ── 顶级评论输入框 ──────────────────────────────────────── */

.comment-form {
  display: grid;
  gap: 12px;
}

.comment-form textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg);
  padding: 12px 14px;
  color: var(--color-text);
  outline: none;
  resize: vertical;
  font-size: 0.93rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.comment-form textarea:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

/* ── 通用复用（main.css 互补类） ─────────────────────────── */

.feedback.error {
  border-radius: 10px;
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 0.88rem;
  margin-bottom: 12px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--color-text-secondary);
}

.empty-state p {
  font-size: 0.93rem;
}

.empty-state a {
  color: var(--color-accent);
  text-decoration: none;
}

/* ── 移动端响应 ──────────────────────────────────────────── */

@media (max-width: 768px) {
  .comments-section {
    padding: 20px 18px;
  }

  .comment-card.comment-reply {
    margin-left: 16px;
  }

  .comment-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
}
</style>