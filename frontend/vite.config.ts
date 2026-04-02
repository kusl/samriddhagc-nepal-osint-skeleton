import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Use environment variable for proxy target (Docker uses backend:8000, local uses localhost:8000)
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
const wsProxyTarget = process.env.VITE_WS_PROXY_TARGET || proxyTarget

// Remove crossorigin attribute from built HTML (causes issues through CDN/tunnel)
function removeCrossOrigin() {
  return {
    name: 'remove-crossorigin',
    transformIndexHtml(html: string) {
      return html.replace(/ crossorigin/g, '')
    }
  }
}

export default defineConfig({
  plugins: [react(), removeCrossOrigin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/react-router-dom/') ||
            id.includes('/framer-motion/')
          ) {
            return 'vendor-react'
          }

          if (
            id.includes('@blueprintjs/') ||
            id.includes('/normalize.css/')
          ) {
            return 'vendor-blueprint'
          }

          if (
            id.includes('/leaflet') ||
            id.includes('/react-leaflet') ||
            id.includes('/react-leaflet-draw') ||
            id.includes('/@turf/')
          ) {
            return 'vendor-geo'
          }

          if (
            id.includes('/cytoscape') ||
            id.includes('/react-cytoscapejs') ||
            id.includes('/vis-data/') ||
            id.includes('/vis-timeline/') ||
            id.includes('/d3/')
          ) {
            return 'vendor-graph'
          }

          if (
            id.includes('/recharts/') ||
            id.includes('/react-countup/')
          ) {
            return 'vendor-charts'
          }

          if (
            id.includes('/axios/') ||
            id.includes('/zustand/') ||
            id.includes('@tanstack/react-query')
          ) {
            return 'vendor-data'
          }

          if (id.includes('/react-markdown/')) {
            return 'vendor-markdown'
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,  // Allow all hosts (nginx uses 'frontend' hostname)
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
    },
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsProxyTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
