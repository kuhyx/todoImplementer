import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineApp } from "@/components/app";
import { defineSessions } from "@/sessions/app";
import { installEventSource, settle, stubFetch } from "@/test/net";
import { defineUsage } from "@/usage/app";
import { defineTable } from "@/usage/table-element";

const tools = (): HTMLElement | null => document.querySelector<HTMLElement>(".phone-tools");

beforeEach(() => {
  vi.useFakeTimers();
  installEventSource();
  stubFetch({});
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok"><meta name="todoimpl-local" content="1">';
  defineApp();
  defineTable();
  defineUsage();
  defineSessions();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe.each([
  ["ti-app", ".usage-host"],
  ["usage-app", ".head"],
  ["sessions-app", ".head"],
])("%s header", (tag, header) => {
  it("carries the phone tools and lets go of the install listeners when removed", async () => {
    const element = document.createElement(tag);
    document.body.append(element);
    await settle(0);
    expect(document.querySelector(`${header} .phone-tools [data-phone="pair"]`)).not.toBeNull();
    const remove = vi.spyOn(globalThis, "removeEventListener");
    element.remove();
    expect(remove).toHaveBeenCalledWith("beforeinstallprompt", expect.any(Function));
  });
});

describe("board header repaints", () => {
  it("keeps the same phone tools node across polls", async () => {
    document.body.append(document.createElement("ti-app"));
    await settle(0);
    const first = tools();
    await settle(30_000);
    expect(first).not.toBeNull();
    expect(tools()).toBe(first);
  });
});
