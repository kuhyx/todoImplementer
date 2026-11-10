import type { Free } from "@/lib/schemas-free";

import { NOW } from "./fixtures.ts";

/** A real-shaped gateway reading (made-up names): one cooling, one failing, one off provider, one nearly spent quota. */
export function makeFree(): Free {
  return {
    at: NOW - 12,
    combo: {
      fallback_pct: 36,
      name: "free-best",
      ok_pct: 99,
      requests: 114,
      steps: [
        { last: NOW - 60, model: "nvidia/nemotron", ok_pct: 100, provider: "nvidia", requests: 48, state: "ok" },
        { last: null, model: "groq/compound", ok_pct: null, provider: "groq", requests: 0, state: "cooling" },
        { last: NOW - 30, model: "openrouter/x:free", ok_pct: 0, provider: "openrouter", requests: 3, state: "failing" },
      ],
    },
    counts: { cooling: 1, failing: 2, ok: 2, providers: 5, quota_known: 1 },
    error: null,
    models: { cooling: 1, total: 364 },
    providers: [
      { failures: 0, id: "nvidia", quota: false, state: "ok", until: null },
      { failures: 1, id: "groq", quota: false, state: "cooling", until: NOW + 90 },
      { failures: 0, id: "openrouter", quota: true, state: "ok", until: null },
      { failures: 2, id: "xkiro", quota: false, state: "failing", until: null },
      { failures: 0, id: "agnes", quota: false, state: "off", until: null },
    ],
    quotas: [
      { label: "free_daily", left_pct: 8, provider: "openrouter", reset_at: NOW + 3600, total: 50, used: 46 },
      { label: "free_rpm", left_pct: 25, provider: "openrouter", reset_at: null, total: 20, used: 15 },
      { label: "free_hour", left_pct: 80, provider: "openrouter", reset_at: null, total: 100, used: 20 },
    ],
    state: "ok",
    tokens: { in: 4_000_000, ours: 812_345, out: 20_000, requests: 163 },
  };
}
