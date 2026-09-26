import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 内网离线部署：不使用任何 CDN，全部资源本地打包。
// 构建目标 es2017，覆盖 Win7 上限浏览器（Chrome/Edge 109、Firefox 115 ESR）
// 以及 macOS/Linux 上的主流近年浏览器。
export default defineConfig({
  plugins: [vue()],
  build: {
    target: 'es2017',
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    chunkSizeWarningLimit: 1536,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
})