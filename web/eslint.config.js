// The shared kuhyx bar (strict type-checked, unicorn all, sonarjs, perfectionist).
// Each override below carries its reason; a rule moves into the preset only once three repos carry the same one.
import { defineConfig } from "@kuhyx/ts-config";

const TEST_FILES = ["src/**/*.test.ts", "src/test/**/*.ts", "dev/**/*.ts"];

export default defineConfig({
  ignores: [".astro/**", "dist/**"],
  overrides: [
    {
      files: ["**/*.ts"],
      rules: {
        // The DOM builder `h(tag, props, ...children)` nests calls by design; flattening trees into
        // temporaries would hide the markup structure the builder exists to show.
        "unicorn/max-nested-calls": "off",
        // `repo` is the wire field name in every contract; `repository` would split the vocabulary
        // between the JSON and the code. res/env/def are the conventional short names in node HTTP and tests.
        "unicorn/name-replacements": [
          "error",
          { replacements: { def: false, env: false, props: false, repo: false, repos: false, res: false } },
        ],
      },
    },
    {
      files: ["src/main.ts"],
      // The page entry exists to run `boot()`; there is nothing to export instead.
      rules: { "unicorn/no-top-level-side-effects": "off" },
    },
    {
      files: ["src/lib/dom.ts"],
      rules: {
        // `must<T extends Element>` is the typed-querySelector pattern: the type parameter IS the return type.
        "@typescript-eslint/no-unnecessary-type-parameters": "off",
        // `class` mirrors the HTML attribute name in the builder's props.
        "unicorn/no-keyword-prefix": "off",
      },
    },
    {
      files: ["dev/**/*.ts"],
      // node:HTTP accepts an async request handler; the mock's route() settles every request itself.
      rules: { "@typescript-eslint/no-misused-promises": "off" },
    },
    {
      files: TEST_FILES,
      rules: {
        // Typed query helpers return the element type the caller names.
        "@typescript-eslint/no-unnecessary-type-parameters": "off",
        // Tests assert on attribute text exactly as the page emits it.
        "unicorn/dom-node-dataset": "off",
        // Node's fs/path default exports are fine in test support.
        "unicorn/import-style": "off",
        // jsdom has no layout: tests install accessor properties on Element.prototype.
        "unicorn/no-this-outside-of-class": "off",
        // Shared harness state (current stub, current drawer) lives at module level and is reset in beforeEach.
        "unicorn/no-top-level-assignment-in-function": "off",
        // Fixtures are written as markup into jsdom; nothing here reaches a real page.
        "unicorn/no-unsafe-dom-html": "off",
        // Test queries run against a throwaway document, scoping them adds noise only.
        "unicorn/prefer-scoped-selector": "off",
      },
    },
  ],
  tsconfigRootDir: import.meta.dirname,
});
