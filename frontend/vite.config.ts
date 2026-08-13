import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000', '/docs': 'http://localhost:8000' } },
})
