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
    // T2520: the default pool built jsdom for every file (90 times) on 23 workers fighting over the 2.4 cores
    // capped.sh grants, 42 s+ on a loaded machine. vmThreads builds it once per worker and still gives each file
    // its own module context; 3 workers measured fastest at the cap (2: 16 s, 3: 10 s, 4: 12 s).
    maxWorkers: 3,
    pool: "vmThreads",
    setupFiles: ["./src/test/setup.ts"],
  },
});
