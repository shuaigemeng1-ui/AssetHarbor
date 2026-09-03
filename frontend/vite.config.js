import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'
  return {
    // 产物以 /static/ 为前缀，与后端 FastAPI 的静态挂载点对齐
    base: '/static/',
    plugins: [vue()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['vue', 'lucide-vue-next'],
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': apiTarget,
        '/i': apiTarget,
        '/v': apiTarget,
        '/healthz': apiTarget,
        '/docs': apiTarget,
      },
    },
  }
})
