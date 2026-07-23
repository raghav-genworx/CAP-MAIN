import { cpSync, createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type Plugin } from "vite";

const workspaceRoot = fileURLToPath(new URL(".", import.meta.url));
const monacoSourceDir = path.join(
  workspaceRoot,
  "node_modules",
  "monaco-editor",
  "min",
  "vs",
);

function contentTypeFor(filePath: string) {
  if (filePath.endsWith(".js")) {
    return "application/javascript";
  }
  if (filePath.endsWith(".css")) {
    return "text/css";
  }
  if (filePath.endsWith(".json")) {
    return "application/json";
  }
  if (filePath.endsWith(".ttf")) {
    return "font/ttf";
  }
  return "application/octet-stream";
}

function localMonacoAssets(): Plugin {
  return {
    name: "local-monaco-assets",
    configureServer(server) {
      server.middlewares.use("/monaco/vs", (request, response, next) => {
        const requestPath = decodeURIComponent(
          request.url?.split("?")[0] ?? "",
        );
        const filePath = path.normalize(path.join(monacoSourceDir, requestPath));
        if (
          !filePath.startsWith(monacoSourceDir) ||
          !existsSync(filePath) ||
          !statSync(filePath).isFile()
        ) {
          next();
          return;
        }

        response.setHeader("Content-Type", contentTypeFor(filePath));
        createReadStream(filePath).pipe(response);
      });
    },
    closeBundle() {
      cpSync(monacoSourceDir, path.join(workspaceRoot, "dist", "monaco", "vs"), {
        recursive: true,
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), localMonacoAssets()],
  server: {
    headers: {
      "Content-Security-Policy": [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://apis.google.com https://www.gstatic.com https://accounts.google.com",
        "connect-src 'self' http://localhost:8000 http://localhost:5173 https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://www.googleapis.com https://accounts.google.com https://firebase.googleapis.com https://firebaseinstallations.googleapis.com",
        "frame-src 'self' https://apis.google.com https://accounts.google.com https://*.firebaseapp.com https://*.google.com",
        "style-src 'self' 'unsafe-inline' https://accounts.google.com",
        "img-src 'self' data: blob: https: https://*.googleusercontent.com https://www.gstatic.com"
      ].join("; ")
    }
  },
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
