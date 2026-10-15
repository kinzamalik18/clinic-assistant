import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In development the API runs separately on port 8000. Proxying keeps the
    // browser on one origin, so the backend needs no CORS settings.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
