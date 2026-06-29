import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("/firebase/") || id.includes("/@firebase/")) {
            return "firebase-vendor";
          }
          if (id.includes("/monaco-editor/")) {
            return "editor-vendor";
          }
          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("/react-router")
          ) {
            return "react-vendor";
          }
          if (
            id.includes("/@reduxjs/") ||
            id.includes("/react-redux/") ||
            id.includes("/@tanstack/")
          ) {
            return "state-vendor";
          }
          if (id.includes("/lucide-react/")) {
            return "icons-vendor";
          }
          if (id.includes("/axios/")) {
            return "http-vendor";
          }
          return undefined;
        },
      },
    },
  },
});
