import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the API runs separately (uvicorn on :8000). In production FastAPI serves dist/ itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
  build: { chunkSizeWarningLimit: 1200 },
});
