import { afterEach, describe, expect, it, vi } from "vitest";

import { stubFetch } from "#fixtures/net";
import { boot } from "@/sessions/boot";

afterEach(() => { vi.unstubAllGlobals(); });

describe("boot", () => {
  it("registers the page element and starts the build watcher", async () => {
    const stub = stubFetch({ "GET /version": { build: "abc1234", version: "0.1.0" } });
    const stop = boot();
    expect(customElements.get("sessions-app")).toBeDefined();
    await vi.waitFor(() => { expect(stub.calls.map((call) => call.url)).toContain("/version"); });
    stop();
    expect(boot()).toBeTypeOf("function");
  });
});
