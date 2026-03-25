import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],

  server: {
    // Proxy нужен для локальной разработки (npm run dev).
    // В Docker те же относительные URL обрабатывает nginx.
    // Без proxy Vite не знает куда отправлять /api/... и /static/... — они идут на :5173,
    // а бэкенд сидит на :8000.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
