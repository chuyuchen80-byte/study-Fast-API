import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  // ── v2.0 新增：开发服务器代理 ──────────────────────────
  // Django 对比：Django 没有跨域问题（前后端同源）
  // Vue 开发服务器默认和 FastAPI 不同端口 → 存在跨域
  // proxy 把 /api 请求转发到 FastAPI 后端，绕过跨域限制
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // /api/user/login → http://127.0.0.1:8000/user/login
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // /static/uploads/xxx.png → http://127.0.0.1:8000/static/uploads/xxx.png
      },
    },
  },
})