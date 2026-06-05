import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

/** same-origin SPA: crossorigin на module script иногда даёт зависший Pending */
function stripCrossOrigin(): Plugin {
  return {
    name: "strip-crossorigin",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace(/ crossorigin/g, "").replace(/ type="module"/g, " defer");
    },
  };
}

export default defineConfig({
  // Один index.html без отдельного .js — обход зависшего Pending на крупном бандле
  plugins: [react(), viteSingleFile(), stripCrossOrigin()],
  base: "/admin/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/uploads": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    cssCodeSplit: false,
  },
});
