<script setup>
/**
 * =============================================================================
 *  ImageUploader.vue —— 图片上传组件（拖拽 + 预览 + 校验）
 * =============================================================================
 *
 * Django 对比：
 *   Django 前端的文件上传通常用原生 <input type="file"> + JS 手写预览
 *   这里封装为独立的 Vue 组件，支持 v-model 双向绑定
 *
 * 使用方式：
 *   <ImageUploader v-model="selectedFiles" :maxFiles="9" :maxSize="5" />
 *
 * 功能：
 *   1. 点击选择 + 拖拽上传
 *   2. 图片预览网格（ObjectURL 临时 URL）
 *   3. 文件类型校验（JPEG / PNG / GIF / WebP）
 *   4. 文件大小校验（默认 5MB 上限）
 *   5. 单张删除按钮
 */

import { ref, watch } from 'vue'

// ── 允许的图片 MIME 类型 ──────────────────────────────────
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

const props = defineProps({
  /** v-model 绑定的文件数组 */
  modelValue: {
    type: Array, // File[]
    default: () => [],
  },
  /** 最大文件数量 */
  maxFiles: {
    type: Number,
    default: 9,
  },
  /** 单文件最大体积（单位 MB） */
  maxSize: {
    type: Number,
    default: 5,
  },
})

const emit = defineEmits(['update:modelValue'])

// ── 内部状态 ──────────────────────────────────────────────

/** 预览 URL 缓存（内存中的临时 URL，组件卸载时需要 revoke） */
const previews = ref([])

/** 校验错误消息 */
const error = ref('')

/** 拖拽悬停状态 */
const isDragging = ref(false)

// ── 同步预览 ──────────────────────────────────────────────

/**
 * 根据当前文件列表重建预览 URL 数组
 * 旧的 ObjectURL 会被 revoke 以防止内存泄漏
 */
function rebuildPreviews() {
  // 释放旧的预览 URL
  previews.value.forEach((url) => URL.revokeObjectURL(url))
  previews.value = props.modelValue.map((f) => URL.createObjectURL(f))
}

// 当外部 v-model 变化时同步预览（如父组件清空了文件列表）
watch(
  () => props.modelValue,
  () => {
    rebuildPreviews()
  },
  { deep: true }
)

// ── 文件校验 ──────────────────────────────────────────────

/**
 * 校验单个文件的类型和大小
 * @param {File} file
 * @returns {string|null} 错误信息，通过校验返回 null
 */
function validateFile(file) {
  if (!ALLOWED_TYPES.includes(file.type)) {
    return `不支持的文件类型：${file.name}（仅支持 JPEG、PNG、GIF、WebP）`
  }
  if (file.size > props.maxSize * 1024 * 1024) {
    return `文件过大：${file.name}（最大 ${props.maxSize}MB）`
  }
  return null
}

// ── 添加文件 ──────────────────────────────────────────────

/**
 * 将新选择的文件追加到当前列表
 * @param {FileList|File[]} newFiles - 来自 input 或拖拽的文件
 */
function addFiles(newFiles) {
  error.value = ''

  const fileArray = Array.from(newFiles)
  if (fileArray.length === 0) return

  // 检查总数是否超标
  const remaining = props.maxFiles - props.modelValue.length
  if (remaining <= 0) {
    error.value = `最多只能上传 ${props.maxFiles} 张图片`
    return
  }

  // 取不超限的文件
  const toAdd = fileArray.slice(0, remaining)
  if (fileArray.length > remaining) {
    error.value = `已超出数量限制，仅添加了前 ${remaining} 张`
  }

  // 逐一校验
  const invalid = toAdd
    .map((f) => validateFile(f))
    .filter(Boolean)

  if (invalid.length > 0) {
    error.value = invalid.join('\n')
    // 只保留通过校验的文件
    const valid = toAdd.filter((f) => !validateFile(f))
    if (valid.length === 0) return
    emit('update:modelValue', [...props.modelValue, ...valid])
  } else {
    emit('update:modelValue', [...props.modelValue, ...toAdd])
  }
}

// ── 删除文件 ──────────────────────────────────────────────

/** 按索引删除单张图片 */
function removeFile(index) {
  const updated = [...props.modelValue]
  updated.splice(index, 1)
  emit('update:modelValue', updated)
}

// ── 事件处理 ──────────────────────────────────────────────

/** 文件选择框 change 事件 */
function onInputChange(e) {
  addFiles(e.target.files)
  // 清空 input 值使得重复选择同一文件仍然触发 change
  e.target.value = ''
}

/** 拖拽进入区域 */
function onDragEnter(e) {
  e.preventDefault()
  isDragging.value = true
}

/** 拖拽离开区域 */
function onDragLeave(e) {
  e.preventDefault()
  isDragging.value = false
}

/** 拖拽悬停（必须阻止默认行为才能触发 drop） */
function onDragOver(e) {
  e.preventDefault()
}

/** 释放文件 */
function onDrop(e) {
  e.preventDefault()
  isDragging.value = false
  addFiles(e.dataTransfer.files)
}
</script>

<template>
  <div class="uploader">
    <!-- ── 拖拽上传区域 ──────────────────────────────── -->
    <div
      class="upload-area"
      :class="{ dragging: isDragging }"
      @dragenter.self="onDragEnter"
      @dragleave.self="onDragLeave"
      @dragover="onDragOver"
      @drop="onDrop"
    >
      <label class="upload-label">
        <span class="upload-hint">
          <span class="upload-icon">&#x1F4C1;</span>
          点击选择图片或拖拽到此处
        </span>
        <span class="upload-note">
          支持 JPEG / PNG / GIF / WebP，单张最大 {{ maxSize }}MB
        </span>
        <input
          type="file"
          multiple
          accept="image/jpeg,image/png,image/gif,image/webp"
          class="upload-input"
          @change="onInputChange"
        />
      </label>
    </div>

    <!-- ── 校验错误提示 ──────────────────────────────── -->
    <div v-if="error" class="upload-error">{{ error }}</div>

    <!-- ── 图片预览网格 ──────────────────────────────── -->
    <div v-if="previews.length" class="preview-grid">
      <div
        v-for="(url, i) in previews"
        :key="url"
        class="preview-item"
      >
        <img :src="url" :alt="`预览图 ${i + 1}`" loading="lazy" />
        <button
          type="button"
          class="btn-remove"
          :title="`移除图片 ${i + 1}`"
          @click="removeFile(i)"
        >
          ×
        </button>
      </div>
      <!-- 已选数量提示 -->
      <div class="preview-count">
        {{ modelValue.length }} / {{ maxFiles }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.uploader {
  display: grid;
  gap: 12px;
}

/* ── 上传区域 ──────────────────────────────────────── */
.upload-area {
  padding: 32px 18px;
  border-radius: 10px;
  background: var(--color-bg);
  border: 2px dashed var(--color-border);
  text-align: center;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.upload-area.dragging {
  border-color: var(--color-accent);
  background: rgba(79, 70, 229, 0.04);
}

.upload-label {
  display: grid;
  gap: 8px;
  cursor: pointer;
  color: var(--color-text-secondary);
}

.upload-hint {
  font-weight: 500;
  font-size: 0.95rem;
}

.upload-icon {
  margin-right: 6px;
}

.upload-note {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

.upload-input {
  display: block;
  margin: 4px auto 0;
  font-size: 0.85rem;
}

/* ── 错误提示 ──────────────────────────────────────── */
.upload-error {
  border-radius: 8px;
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 0.85rem;
  white-space: pre-line;
}

/* ── 预览网格 ──────────────────────────────────────── */
.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
}

.preview-item {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  aspect-ratio: 1;
  border: 1px solid var(--color-border);
}

.preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.btn-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}

.btn-remove:hover {
  background: var(--color-danger);
}

.preview-count {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px dashed var(--color-border);
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  aspect-ratio: 1;
}
</style>