/** Shared setup of the sessions page tests: fake clock, routed fetch, CSRF meta, clipboard, a mounted <sessions-app>. */
import { vi } from "vitest";

import type { Session } from "@/sessions/schemas";

import { result, sessionList, sessionRows } from "#fixtures/fixture-sessions";
import { type FetchStub, stubFetch } from "#fixtures/net";
import { defineSessions,  SessionsApp } from "@/sessions/app";



export interface Harness {
  app: SessionsApp;
  posts: () => { body: unknown; headers: unknown; url: string }[];
  rows: Session[];
  stub: FetchStub;
}

export async function flush(): Promise<void> {
  for (let index = 0; index < 6; index += 1) await vi.advanceTimersByTimeAsync(0);
}

export function setToken(token: null | string): void {
  document.head.querySelector('meta[name="todoimpl-csrf"]')?.remove();
  if (token === null) return;
  const meta = document.createElement("meta");
  meta.name = "todoimpl-csrf";
  meta.content = token;
  document.head.append(meta);
}

export function useClipboard(write = vi.fn().mockResolvedValue(undefined)): ReturnType<typeof vi.fn> {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: write } });
  return write;
}

export function install(): void {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-20T08:00:00.000Z"));
  defineSessions();
  setToken("tok");
}

export function uninstall(): void {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  globalThis.location.hash = "";
}

export interface Options {
  /** Replaces the list route (to fail it, say). */
  list?: () => unknown;
  /** The answer of every POST (default: ok). */
  reply?: unknown;
  rows?: Session[];
}

/** Mount the page over a mutable list. */
export async function mount(hash = "", options: Options = {}): Promise<Harness> {
  const harness = { rows: options.rows ?? sessionRows() } as Harness;
  const reply = options.reply ?? result();
  harness.stub = stubFetch({
    "GET /api/sessions": options.list ?? (() => sessionList(harness.rows)),
    "POST /api/sessions/delete": () => reply,
    "POST /api/sessions/mark": () => reply,
    "POST /api/sessions/resume": () => reply,
  });
  harness.posts = () => {
    return harness.stub.calls
      .filter((call) => call.init?.method === "POST")
      .map((call) => ({ body: JSON.parse(call.init?.body as string) as unknown, headers: call.init?.headers, url: call.url }));
  };
  globalThis.location.hash = hash;
  harness.app = new SessionsApp();
  document.body.replaceChildren(harness.app);
  await flush();
  return harness;
}

export const ids = (app: Element): string[] => [...app.querySelectorAll("tr[data-id]")].map((row) => (row as HTMLElement).dataset.id ?? "");
export const q = <T extends Element = HTMLElement>(app: Element, selector: string): T => app.querySelector<T>(selector)!;
export const qa = <T extends Element = HTMLElement>(app: Element, selector: string): T[] => [...app.querySelectorAll<T>(selector)];
export const click = async (element: Element, init: MouseEventInit = {}): Promise<void> => {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ...init }));
  await flush();
};

export {POLL_MS} from "@/sessions/app";