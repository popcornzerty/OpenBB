import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5180,
    strictPort: true,
    watch: {
      // `src-tauri/target` est réécrit en permanence pendant une compilation
      // Rust ; le surveiller fait tomber Vite avec EBUSY dès que cargo tient
      // un fichier ouvert.
      ignored: ["**/src-tauri/**"],
    },
    // Le backend tourne en local ; passer par un proxy évite d'avoir à gérer
    // le CORS différemment entre le serveur de développement et la webview Tauri.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8801",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "esnext",
    outDir: "dist",
  },
});
