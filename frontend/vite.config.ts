import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

function isNodePackage(id: string, packageName: string) {
  return (
    id.includes(`/node_modules/${packageName}/`) ||
    id.includes(`/node_modules/.pnpm/${packageName.replace('/', '+')}@`)
  )
}

// https://vite.dev/config/
export default defineConfig({
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (error, request) => {
            console.warn('[vite-proxy] /api request failed', {
              method: request.method,
              url: request.url,
              code: (error as NodeJS.ErrnoException).code,
              message: error.message,
            })
          })
          proxy.on('proxyRes', (proxyRes) => {
            delete proxyRes.headers['content-length']
          })
        },
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
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('/node_modules/')) {
            return
          }

          if (isNodePackage(id, '@affino/datagrid-vue-app')) {
            return 'vendor-affino-datagrid-app'
          }

          if (
            isNodePackage(id, '@affino/datagrid-chrome') ||
            isNodePackage(id, '@affino/datagrid-gantt')
          ) {
            return 'vendor-affino-datagrid-features'
          }

          if (
            isNodePackage(id, '@affino/datagrid-format') ||
            isNodePackage(id, '@affino/datagrid-server-adapters') ||
            isNodePackage(id, '@affino/datagrid-server-client') ||
            isNodePackage(id, '@affino/datagrid-theme')
          ) {
            return 'vendor-affino-datagrid-shared'
          }

          if (isNodePackage(id, '@affino/datagrid-core')) {
            return 'vendor-affino-datagrid-core'
          }

          if (
            isNodePackage(id, '@affino/datagrid-formula-engine') ||
            isNodePackage(id, '@affino/datagrid-orchestration') ||
            isNodePackage(id, '@affino/datagrid-pivot') ||
            isNodePackage(id, '@affino/datagrid-plugins') ||
            isNodePackage(id, '@affino/datagrid-worker')
          ) {
            return 'vendor-affino-datagrid-engine'
          }

          if (isNodePackage(id, '@affino/datagrid-vue')) {
            return 'vendor-affino-datagrid-vue'
          }

          if (
            isNodePackage(id, '@affino/dialog-core') ||
            isNodePackage(id, '@affino/dialog-vue')
          ) {
            return 'vendor-affino-dialog'
          }

          if (
            isNodePackage(id, '@affino/focus-utils') ||
            isNodePackage(id, '@affino/menu-core') ||
            isNodePackage(id, '@affino/menu-vue') ||
            isNodePackage(id, '@affino/overlay-host') ||
            isNodePackage(id, '@affino/overlay-kernel') ||
            isNodePackage(id, '@affino/popover-core') ||
            isNodePackage(id, '@affino/popover-vue') ||
            isNodePackage(id, '@affino/tooltip-core') ||
            isNodePackage(id, '@affino/tooltip-vue')
          ) {
            return 'vendor-affino-overlays'
          }

          if (
            isNodePackage(id, '@affino/combobox-core') ||
            isNodePackage(id, '@affino/combobox-vue')
          ) {
            return 'vendor-affino-combobox'
          }

          if (
            id.includes('/node_modules/@affino/') ||
            id.includes('/node_modules/.pnpm/@affino+')
          ) {
            return 'vendor-affino'
          }

          if (
            isNodePackage(id, 'vue') ||
            isNodePackage(id, '@vue/compiler-core') ||
            isNodePackage(id, '@vue/compiler-dom') ||
            isNodePackage(id, '@vue/compiler-sfc') ||
            isNodePackage(id, '@vue/reactivity') ||
            isNodePackage(id, '@vue/runtime-core') ||
            isNodePackage(id, '@vue/runtime-dom') ||
            isNodePackage(id, '@vue/server-renderer') ||
            isNodePackage(id, '@vue/shared') ||
            isNodePackage(id, 'pinia') ||
            isNodePackage(id, 'vue-router')
          ) {
            return 'vendor-vue'
          }

          return
        },
      },
    },
  },
})
