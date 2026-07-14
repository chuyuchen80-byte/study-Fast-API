/**
 * =============================================================================
 *  api/client.js —— 集中化 HTTP 请求客户端（Django 前端的 axios instance 对应物）
 * =============================================================================
 *
 * Django 对比：
 *   前端通常用 axios.create({ baseURL: '/api' }) 创建一个 instance，统一管理
 *   这里我们手动封装 fetch，达到类似效果
 *
 * 核心功能：
 *   1. 统一的 base URL 配置（从环境变量读取，不再硬编码）
 *   2. 统一的 Authorization 头注入（从 Pinia auth store 读取 token）
 *   3. 统一的错误处理（401 自动清除登录状态）
 *   4. 统一的 JSON 解析 + 中文错误信息提取
 *   5. FormData 支持（文件上传不用 JSON Content-Type）
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

/**
 * 核心请求函数 —— 所有 API 调用的唯一入口
 *
 * 对比之前的代码：4 个组件里各有一份 request()，只是 token 传入方式不同
 * 现在统一到这里，token 直接从 Pinia store 读取，组件不需要关心
 *
 * @param {string} path - API 路径，如 '/user/login'（不带 base URL）
 * @param {object} options
 * @param {string} options.method - HTTP 方法，默认 'GET'
 * @param {object} options.payload - 请求体（JSON 对象 或 FormData）
 * @param {boolean} options.isFormData - payload 是否为 FormData（文件上传）
 * @param {boolean} options.skipAuth - 跳过附加 token（登录/注册不需要 token）
 * @returns {Promise<any>} 解析后的响应数据
 * @throws {Error} 请求失败时抛出带 detail 信息的 Error
 */
export async function request(path, {
  method = 'GET',
  payload,
  isFormData = false,
  skipAuth = false,
} = {}) {
  const headers = {}

  // 非 FormData 请求才设 Content-Type（浏览器会自动给 FormData 设 multipart boundary）
  if (!isFormData && payload && method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }

  // 从 Pinia store 读取 token（而不是从 props 一层层传递）
  // 动态 import 避免循环依赖 —— useAuthStore 内部可能 import api/client
  // v2.0.1 修复：去掉 && !isFormData，FormData 请求也需要 token！
  // 之前 BUG: skipAuth=false + isFormData=true → token 不附加 → 401
  if (!skipAuth) {
    try {
      const { useAuthStore } = await import('@/stores/auth')
      const auth = useAuthStore()
      if (auth.token) {
        headers.Authorization = `Bearer ${auth.token}`
      }
    } catch {
      // store 还没初始化（如登录页面），忽略
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isFormData
      ? payload
      : payload && method !== 'GET'
        ? JSON.stringify(payload)
        : undefined,
  })

  // 204 No Content（DELETE 成功等）—— 无响应 body
  if (response.status === 204) return null

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    // 401 → 通知 auth store 清除登录状态
    if (response.status === 401) {
      try {
        const { useAuthStore } = await import('@/stores/auth')
        useAuthStore().logout()
      } catch { /* store 未初始化 */ }
    }
    throw new Error(data.detail || `请求失败 (${response.status})`)
  }

  return data
}

/**
 * 上传文件专用函数（封装 FormData 构造）
 *
 * @param {string} path - API 路径
 * @param {object} fields - 普通表单字段 { title: 'xxx', content: 'yyy' }
 * @param {File[]} files - 文件数组
 * @param {string} fileFieldName - 文件字段名，默认 'files'
 * @returns {Promise<any>}
 */
export async function uploadRequest(path, fields = {}, files = [], fileFieldName = 'files') {
  const formData = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    formData.append(key, value)
  }
  for (const file of files) {
    formData.append(fileFieldName, file)
  }
  return request(path, { method: 'POST', payload: formData, isFormData: true })
}

// ── 便捷方法 ──────────────────────────────────────────────

export const api = {
  get: (path) => request(path, { method: 'GET' }),
  post: (path, payload) => request(path, { method: 'POST', payload }),
  put: (path, payload) => request(path, { method: 'PUT', payload }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: uploadRequest,
}