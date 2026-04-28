import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

function normalizeBasePath(value: string) {
  const trimmed = value.trim()
  if (!trimmed || trimmed === '/') return '/'
  const withoutEdgeSlashes = trimmed.replace(/^\/+|\/+$/g, '')
  return `/${withoutEdgeSlashes}/`
}

const appBasePath = normalizeBasePath(
  process.env.VITE_APP_BASE_PATH ?? (process.env.NODE_ENV === 'production' ? '/auctions/' : '/'),
)

// https://vite.dev/config/
export default defineConfig({
  base: appBasePath,
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
})
