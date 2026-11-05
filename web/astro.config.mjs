import { defineConfig } from "astro/config";
import { fileURLToPath } from "node:url";

// One static page served from the root of the loopback server (and Caddy).
// Scripts stay external files: the server's CSP is `default-src 'self'`.
export default defineConfig({
  build: { assets: "assets", inlineStylesheets: "never" },
  devToolbar: { enabled: false },
  outDir: "dist",
  server: { host: "127.0.0.1", port: 4321 },
  vite: {
    build: { assetsInlineLimit: 0 },
    resolve: { alias: { "@": fileURLToPath(new URL("src", import.meta.url)) } },
    server: { proxy: { "/api": "http://127.0.0.1:8786", "/version": "http://127.0.0.1:8786" } },
  },
});
