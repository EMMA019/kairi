import os

file_path = r"d:\program\chat\frontend\vite.config.ts"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import_replacement = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
"""
if "VitePWA" not in content:
    content = content.replace("import tailwindcss from '@tailwindcss/vite'", "import tailwindcss from '@tailwindcss/vite'\nimport { VitePWA } from 'vite-plugin-pwa'")

plugins_target = "plugins: [react(), tailwindcss()],"
plugins_replacement = """plugins: [
    react(), 
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons.svg'],
      manifest: {
        name: 'Kairi Chat AI',
        short_name: 'Kairi',
        description: 'Autonomous AI Agent with Chat & IDE',
        theme_color: '#0b0e14',
        background_color: '#0b0e14',
        display: 'standalone',
        icons: [
          {
            src: 'favicon.svg',
            sizes: '192x192 512x512',
            type: 'image/svg+xml'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,json}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-cache',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] }
            }
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'gstatic-fonts-cache',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] }
            }
          }
        ]
      }
    })
  ],"""

if "VitePWA(" not in content:
    content = content.replace(plugins_target, plugins_replacement)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("vite.config.ts patched successfully.")
