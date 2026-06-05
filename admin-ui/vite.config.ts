import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/** same-origin SPA: crossorigin на module script иногда даёт зависший Pending */
function stripCrossOrigin(): Plugin {
  return {
    name: "strip-crossorigin",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace(/ crossorigin/g, "");
    },
  };
}

export default defineConfig({
  plugins: [react(), stripCrossOrigin()],
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
  },
});
