import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { showToast } from "@/components/feedback";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("toast dedupe", () => {
  it("[T802] identical text shows one toast while visible, again once it is gone", () => {
    for (let n = 0; n < 3; n += 1) showToast("live stage: unexpected shape", "error");
    showToast("other", "error");
    const region = document.querySelector("#toasts");
    expect(region?.children).toHaveLength(2);
    vi.advanceTimersByTime(13_000);
    expect(region?.children).toHaveLength(0);
    showToast("live stage: unexpected shape", "error");
    expect(region?.children).toHaveLength(1);
  });
});
