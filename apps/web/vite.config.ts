// Vite settings. `npm run dev` forwards /api, /ws and /healthz to the backend, so the app always calls
// its own origin (THE SHARED CONTRACT, C0). In production nginx does the same (nginx/default.conf.template).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.MOCHI_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      "/healthz": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
});
