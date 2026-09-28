import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the API runs separately (uvicorn on :8000). In production FastAPI serves dist/ itself.
const apiTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": apiTarget, "/health": apiTarget },
  },
  build: { chunkSizeWarningLimit: 1200 },
});
