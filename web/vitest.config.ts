/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";
import { fileURLToPath } from "node:url";

// Tests run under Astro's Vite config so the `@/` alias and CSS imports
// resolve the way they do in the build. `.astro` files are markup, covered by
// the page-shell test; src/test is test support, not product code.
export default getViteConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("src", import.meta.url)) } },
  test: {
    coverage: {
      exclude: ["src/test/**", "src/**/*.test.ts", "src/**/*.d.ts"],
      include: ["src/**/*.ts"],
      provider: "v8",
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.ts"],
    setupFiles: ["./src/test/setup.ts"],
  },
});
