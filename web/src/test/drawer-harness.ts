/** Shared setup for the drawer tests: a mounted <ti-drawer>, fake timers, EventSource and a routed fetch. */
import { afterEach, beforeEach, vi } from "vitest";

import type { TaskCard } from "@/lib/schemas-common";

import { defineDrawer, TiDrawer } from "@/components/drawer";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";
import { type FetchStub, installEventSource, settle, stubFetch } from "@/test/net";

export const card = (status: string): TaskCard => {
  const found = makeCards().find((c) => c.status === status);
  if (found === undefined) throw new Error(status);
  return found;
};
export const json = (body: unknown, status = 200): Response => Response.json(body, { status });
export const q = <T extends Element = HTMLElement>(sel: string): T => {
  const element = document.querySelector<T>(sel);
  if (element === null) throw new Error(`no ${sel}`);
  return element;
};
export const fail = (message: string, code = "disabled", status = 409): (() => Response) => {
  return () =>
    json({ error: { code, message }, ok: false }, status);
};

export const env = { drawer: undefined as unknown as TiDrawer, stub: undefined as unknown as FetchStub };

export async function open(c: TaskCard, extra: Record<string, unknown> = {}): Promise<void> {
  env.stub = stubFetch({ [`GET /api/task/${c.id}`]: () => makeDetail(c), ...extra });
  env.drawer.open(c.id, document.querySelector("#opener"));
  await settle(0);
}

export function useDrawerHarness(): void {
  beforeEach(() => {
    vi.useFakeTimers();
    installEventSource();
    document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok123">';
    document.body.innerHTML = '<button id="opener">card</button>';
    defineDrawer();
    defineDrawer();
    env.drawer = new TiDrawer();
    document.body.append(env.drawer);
  });

  afterEach(() => {
    env.drawer.close(false);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    document.body.replaceChildren();
    document.head.replaceChildren();
  });
}
