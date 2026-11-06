/** `#/<view>[/<arg>][?filters&t.<table>.*]`: the whole page state lives in the hash (R3). */
export type ViewId = "ab" | "anomalies" | "autonomy" | "context" | "efficiency" | "f" | "items" | "levers" | "more" | "overview" | "s" | "sessions";

export interface View {
  id: ViewId;
  label: string;
}

export const VIEWS: readonly View[] = [
  { id: "overview", label: "Spend" },
  { id: "sessions", label: "Sessions" },
  { id: "items", label: "Per todo item" },
  { id: "efficiency", label: "Efficiency" },
  { id: "autonomy", label: "Autonomy" },
  { id: "levers", label: "Levers" },
  { id: "context", label: "Context files" },
  { id: "anomalies", label: "Anomalies" },
  { id: "ab", label: "A/B" },
  { id: "more", label: "More panels" },
];

/** Routes with an argument and no tab of their own: a session, a context file, one generic panel. */
const KNOWN = new Set<string>([...VIEWS.map((view) => view.id), "f", "s"]);
const TAKES_ARGUMENT = new Set<string>(["f", "more", "s"]);
const isView = (value: string): value is ViewId => KNOWN.has(value);

export interface Route {
  arg: string;
  parameters: URLSearchParams;
  view: ViewId;
}

export function parseRoute(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/v, "").split("?", 2);
  const [head = "", ...rest] = path.split("/");
  const argument = decodeURIComponent(rest.join("/"));
  const parameters = new URLSearchParams(query);
  if (!isView(head)) return { arg: "", parameters, view: "overview" };
  const isTakesArgument = TAKES_ARGUMENT.has(head);
  return { arg: isTakesArgument ? argument : "", parameters, view: head };
}

/** `path?query`, or just `path` when the query is empty. */
export function withQuery(path: string, query: string): string {
  return query === "" ? path : `${path}?${query}`;
}

export function formatRoute(route: Route): string {
  const path = route.arg === "" ? route.view : `${route.view}/${encodeURIComponent(route.arg)}`;
  const query = route.parameters.toString();
  return `#/${withQuery(path, query)}`;
}

/** Link to a session / file / panel, carrying the page's global filters but no table state. */
export function linkTo(view: ViewId, argument: string, parameters: URLSearchParams): string {
  const kept = new URLSearchParams([...parameters].filter(([key]) => !key.startsWith("t.")));
  return formatRoute({ arg: argument, parameters: kept, view });
}

/** The tab that lights up for a route (a session belongs to Sessions, a file to Context files). */
export function tabFor(view: ViewId): ViewId {
  if (view === "s") return "sessions";
  return view === "f" ? "context" : view;
}
