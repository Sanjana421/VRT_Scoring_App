import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // In dev (npm run dev on :5173), proxy /api to FastAPI on :8000
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Relative to this frontend folder. In the combined repo the frontend lives
    // at Score_Data/frontend, so this builds into Score_Data/frontend/dist,
    // which is exactly what the FastAPI backend serves.
    outDir: 'dist',
    emptyOutDir: true,
  },
})
