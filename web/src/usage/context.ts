import { filterQuery } from "@/usage/api";
import { linkTo, type ViewId } from "@/usage/route";
import { readTable, type TableState, writeTable } from "@/usage/table-model";

export interface Context {
  filters: () => URLSearchParams;
  href: (view: ViewId, argument?: string) => string;
  read: (id: string) => TableState;
  write: (id: string, state: TableState) => void;
}

/** Context over a live hash. `write` uses replaceState so typing never pushes history or re-renders the view. */
export function hashContext(win: Pick<Window, "history" | "location"> = globalThis): Context {
  const parameters = (): URLSearchParams => new URLSearchParams(win.location.hash.split("?", 2)[1] ?? "");
  return {
    filters: () => filterQuery(parameters()),
    href: (view, argument = "") => linkTo(view, argument, parameters()),
    read: (id) => readTable(parameters(), id),
    write: (id, state) => {
      const { hash } = win.location;
      const mark = hash.indexOf("?");
      const path = mark === -1 ? hash : hash.slice(0, mark);
      const query = writeTable(parameters(), id, state).toString();
      const suffix = query === "" ? "" : `?${query}`;
      win.history.replaceState(null, "", `${win.location.pathname}${win.location.search}${path === "" ? "#/overview" : path}${suffix}`);
    },
  };
}

/** In-memory twin of `hashContext` for tests and static renders. */
export function memoryContext(initial = ""): Context & { hash: () => string } {
  let parameters = new URLSearchParams(initial);
  return {
    filters: () => filterQuery(parameters),
    hash: () => parameters.toString(),
    href: (view, argument = "") => linkTo(view, argument, parameters),
    read: (id) => readTable(parameters, id),
    write: (id, state) => {
      parameters = writeTable(parameters, id, state);
    },
  };
}
