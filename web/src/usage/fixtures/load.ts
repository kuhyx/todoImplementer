/** Real-shaped payloads captured read-only from the old control-panel API (items.json is hand-made: that endpoint is new). */
import ab from "./ab.json";
import anomalies from "./anomalies.json";
import contextFile from "./context-file.json";
import context from "./context.json";
import efficiency from "./efficiency.json";
import hooks from "./hooks.json";
import index from "./index.json";
import items from "./items.json";
import levers from "./levers.json";
import overview from "./overview.json";
import session from "./session.json";
import sessions from "./sessions.json";

export const fixtures = { ab, anomalies, context, contextFile, efficiency, hooks, index, items, levers, overview, session, sessions };

/** A fetch stub answering each /api/tokens URL with the matching fixture. */
export function fakeFetch(routes: Record<string, unknown> = {}): typeof fetch {
  const table: Record<string, unknown> = {
    "/api/tokens": fixtures.index,
    "/api/tokens/context-file": fixtures.contextFile,
    "/api/tokens/items": fixtures.items,
    "/api/tokens/panel/ab": fixtures.ab,
    "/api/tokens/panel/anomalies": fixtures.anomalies,
    "/api/tokens/panel/context": fixtures.context,
    "/api/tokens/panel/efficiency": fixtures.efficiency,
    "/api/tokens/panel/hooks": fixtures.hooks,
    "/api/tokens/panel/levers": fixtures.levers,
    "/api/tokens/panel/overview": fixtures.overview,
    "/api/tokens/panel/sessions": fixtures.sessions,
    session: fixtures.session,
    ...routes,
  };
  return ((input: string) => {
    const url = new URL(input, "https://x.invalid");
    const key = url.pathname.startsWith("/api/tokens/session/") ? "session" : url.pathname;
    const body = table[key];
    return Promise.resolve(Response.json(body ?? { error: "no such endpoint" }, { status: body === undefined ? 404 : 200 }));
  }) as unknown as typeof fetch;
}
