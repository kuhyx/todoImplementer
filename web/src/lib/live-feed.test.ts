import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openLive } from "@/lib/live-feed";
import { liveEvent } from "@/lib/schemas";
import { contractValidator } from "@/test/contract-ajv";
import { installEventSource, lastSource } from "@/test/net";

/** The stage frame a running card sends (cancel with confirm, send, copy-resume with value), made-up ids. */
const RUNNING_STAGE = {
  actions: [
    { confirm: true, enabled: true, id: "cancel", label: "Cancel", reason: null },
    { enabled: true, id: "send", label: "Send to Claude", reason: null },
    { enabled: true, id: "copy-resume", label: "Copy resume command", reason: null, value: "cd /tmp/wt && claude --resume 0a1b2c3d" },
  ],
  column: "running",
  current: "implement",
  needs: null,
  stage: "implement",
  status: "working",
  type: "stage",
};

beforeEach(() => {
  installEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const setup = () => {
  const handlers = { onBad: vi.fn(), onEvent: vi.fn(), onState: vi.fn() };
  openLive("17a1b2c3-0", handlers);
  return { handlers, source: lastSource() };
};

describe("live stage contract", () => {
  it("a real running stage frame parses in the JSON schema and in Zod", () => {
    expect(contractValidator("live")(RUNNING_STAGE)).toBe(true);
    expect(liveEvent.safeParse(RUNNING_STAGE).success).toBe(true);
    const { handlers, source } = setup();
    source.emit("stage", RUNNING_STAGE);
    expect(handlers.onBad).not.toHaveBeenCalled();
    expect(handlers.onEvent).toHaveBeenCalledWith(RUNNING_STAGE);
  });

  it("[T104] the connect snapshot of a card never run (stage null) parses in both", () => {
    const backlog = {
      actions: [{ enabled: true, id: "start", label: "Start", reason: null }],
      column: "backlog",
      current: "not started",
      needs: null,
      stage: null,
      status: "backlog",
      type: "stage",
    };
    expect(contractValidator("live")(backlog)).toBe(true);
    const { handlers, source } = setup();
    source.emit("stage", backlog);
    expect(handlers.onBad).not.toHaveBeenCalled();
    expect(handlers.onEvent).toHaveBeenCalledWith(backlog);
  });
});

describe("bad live frames", () => {
  it("[T801] name the Zod path and expected/received, and warn with the raw payload", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { handlers, source } = setup();
    const bad = { ...RUNNING_STAGE, actions: [{ ...RUNNING_STAGE.actions[0], label: 5 }] };
    source.emit("stage", bad);
    expect(handlers.onBad).toHaveBeenCalledTimes(1);
    const message = String((handlers.onBad.mock.calls[0] as unknown[])[0]);
    expect(message).toMatch(/^live stage: actions\[0\]\.label: .*expected string.*number/);
    expect(warn).toHaveBeenCalledWith("live stage: bad payload", bad, expect.any(Array));
  });

  it("[T801] a missing field is named at the root and extra issues are counted", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { handlers, source } = setup();
    source.emit("cost", { type: "cost" });
    source.emit("stage", { type: "stage" });
    source.emit("done", 5);
    const [first, second, third] = handlers.onBad.mock.calls.map((call: unknown[]) => String(call[0]));
    expect(first).toMatch(/^live cost: cost_usd: /);
    expect(second).toMatch(/^live stage: actions: .*\(\+\d+ more\)$/);
    expect(third).toMatch(/^live done: \(root\): /);
  });
});
