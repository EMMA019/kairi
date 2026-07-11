import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  publicDir: '../public',   // ← これが一番大事！ frontend/public をpublicフォルダとして使う
  base: '/',
  server: {
    port: 5173,
    open: true
  }
})