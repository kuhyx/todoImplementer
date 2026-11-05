/** Test doubles for the network edge: a routed fetch and a scriptable EventSource. */
import { vi } from "vitest";

export type Handler = (init: RequestInit | undefined, url: string) => unknown;

export interface FetchStub {
  calls: { init: RequestInit | undefined; url: string }[];
  routes: Map<string, Handler>;
}

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { headers: { "Content-Type": "application/json" }, status });
}

/** `routes` maps "METHOD path" (path without query) to a body or a function returning a body / Response. */
export function stubFetch(routes: Record<string, unknown>): FetchStub {
  const stub: FetchStub = { calls: [], routes: new Map() };
  for (const [key, value] of Object.entries(routes)) {
    stub.routes.set(key, typeof value === "function" ? (value as Handler) : () => value);
  }
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = input;
      stub.calls.push({ init, url });
      const method = init?.method ?? "GET";
      const handler = stub.routes.get(`${method} ${url.split("?", 1)[0] ?? url}`);
      if (handler === undefined) return jsonResponse({ missing: url }, 404);
      const result = await handler(init, url);
      if (result instanceof Response) return result;
      if (Error.isError(result)) throw result;
      return jsonResponse(result);
    }),
  );
  return stub;
}

export class FakeEventSource {
  static readonly instances: FakeEventSource[] = [];
  static readonly CLOSED = 2;
  closed = false;
  readyState = 0;
  readonly listeners = new Map<string, ((event: Event) => void)[]>();
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(type: string, data?: unknown): void {
    const event = data === undefined ? new Event(type) : new MessageEvent(type, { data: typeof data === "string" ? data : JSON.stringify(data) });
    const listeners = this.listeners.get(type);
    if (listeners === undefined) return;
    for (const listener of listeners) listener(event);
  }
}

export function installEventSource(): void {
  FakeEventSource.instances.length = 0;
  vi.stubGlobal("EventSource", FakeEventSource);
}

export const lastSource = (): FakeEventSource => {
  const source = FakeEventSource.instances.at(-1);
  if (source === undefined) throw new Error("no EventSource opened");
  return source;
};

export const settle = async (ms: number): Promise<void> => {
  await vi.advanceTimersByTimeAsync(ms);
};
