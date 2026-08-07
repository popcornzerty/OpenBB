import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Port du serveur de développement, et backend qu'il relaie.
 *
 *  Les deux sont paramétrables pour qu'une seconde instance puisse tourner
 *  en parallèle — comparer deux versions du terminal côte à côte suppose de
 *  ne pas se disputer les mêmes ports.
 *
 *      $env:PEATERM_DEV_PORT = 5181
 *      $env:PEATERM_API_TARGET = "http://127.0.0.1:8802"
 *      npm run dev
 */
const port = Number(process.env.PEATERM_DEV_PORT ?? 5180);
const target = process.env.PEATERM_API_TARGET ?? "http://127.0.0.1:8801";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port,
    // Échouer bruyamment plutôt que glisser sur un autre port : on saurait
    // sinon jamais laquelle des deux instances on consulte.
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
        target,
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "esnext",
    outDir: "dist",
  },
});
