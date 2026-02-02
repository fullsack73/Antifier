import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        // couldn't afford a hosting service, so use local machine
        target: 'http://localhost:5000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    },
    // free version ngrok. again, couldn't afford a paid version
    allowedHosts: ['gannet-included-jolly.ngrok-free.app']
  },
  test: {
    globals: true,
    environment: 'jsdom'
  }
})
