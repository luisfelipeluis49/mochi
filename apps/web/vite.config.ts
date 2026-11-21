// =============================================================================
// vite.config.ts  —  LANGUAGE: TypeScript (settings for Vite, the tool that runs the app)
// -----------------------------------------------------------------------------
// `npm run dev` reads this file. It turns on React and sets up "forwarding":
// any request the page makes to /api, /dev or /ws goes to the backend instead.
// =============================================================================
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the backend runs on :8000 (scripts/start-dev.sh).
// The proxy lets the pages call /api and /ws on the same origin.
const backend = process.env.MOCHI_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, // the app opens at http://localhost:5173
    proxy: {
      "/api": backend,
      "/dev": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true }, // ws: true = also forward WebSockets
    },
  },
});
