import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 本地开发：vite 代理到后端 uvicorn（默认 8080），前后端分离调试
export default defineConfig({
  // 产物以 /static/ 为前缀，与后端 FastAPI 的静态挂载点对齐
  base: '/static/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/i': 'http://localhost:8080',
      '/healthz': 'http://localhost:8080',
      '/docs': 'http://localhost:8080',
    },
  },
})
