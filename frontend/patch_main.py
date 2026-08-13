import os

file_path = r"d:\program\chat\frontend\src\main.tsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import_replacement = """import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { registerSW } from 'virtual:pwa-register'

const updateSW = registerSW({
  onNeedRefresh() {
    if (confirm('新しいバージョンが利用可能です。更新しますか？')) {
      updateSW(true)
    }
  },
  onOfflineReady() {
    console.log('App ready to work offline')
  },
})
"""

if "virtual:pwa-register" not in content:
    content = content.replace("import { ErrorBoundary } from './components/ErrorBoundary'", import_replacement)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("main.tsx patched successfully.")
