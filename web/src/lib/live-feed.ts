/** SSE client for /api/live?id=: every payload is Zod-parsed and a bad one is reported, never dropped. */
import type { z } from "zod";

import { routes } from "@/lib/routes";
import { type LiveEvent, liveEvent } from "@/lib/schemas";

export type LiveState = "closed" | "connecting" | "live" | "reconnecting";

export interface LiveHandlers {
  onBad: (message: string) => void;
  onEvent: (event: LiveEvent) => void;
  onState: (state: LiveState) => void;
}

const TYPES = ["activity", "stage", "cost", "done"] as const;

function pathText(path: readonly PropertyKey[]): string {
  let text = "";
  for (const key of path) {
    if (typeof key === "number") text += `[${String(key)}]`;
    else text += text === "" ? String(key) : `.${String(key)}`;
  }
  return text === "" ? "(root)" : text;
}

/** `live stage: actions[0].label: Invalid input: expected string, received number (+2 more)`: the first issue, counted. */
function issueText(type: string, issues: readonly z.core.$ZodIssue[]): string {
  const line = issues.slice(0, 1).map((issue) => `${pathText(issue.path)}: ${issue.message}`).join("");
  const more = issues.length > 1 ? ` (+${String(issues.length - 1)} more)` : "";
  return `live ${type}: ${line}${more}`;
}

export function openLive(id: string, handlers: LiveHandlers): () => void {
  const source = new EventSource(routes.live(id));
  handlers.onState("connecting");
  source.addEventListener("open", () => {
    handlers.onState("live");
  });
  source.addEventListener("error", () => {
    handlers.onState(source.readyState === EventSource.CLOSED ? "closed" : "reconnecting");
  });
  for (const type of TYPES) {
    source.addEventListener(type, (message) => {
      let data: unknown;
      try {
        data = JSON.parse((message as MessageEvent<string>).data) as unknown;
      } catch {
        handlers.onBad(`live ${type}: not JSON`);
        return;
      }
      const parsed = liveEvent.safeParse(data);
      if (!parsed.success) {
        console.warn(`live ${type}: bad payload`, data, parsed.error.issues);
        handlers.onBad(issueText(type, parsed.error.issues));
        return;
      }
      handlers.onEvent(parsed.data);
      if (parsed.data.type !== "done") {
        return;
      }

      source.close();
      handlers.onState("closed");
    });
  }
  return () => {
    source.close();
  };
}
