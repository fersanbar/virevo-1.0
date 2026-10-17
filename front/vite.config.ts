import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, todo lo que empiece con /api se reenvía al backend (puerto 8000).
// Así el navegador no se queja de CORS y la URL del backend vive en un solo lugar.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
