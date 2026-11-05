/** Every URL and POST body shape in one place (contracts/requests.schema.json). */
import type { ActionId } from "@/lib/schemas-common";

export const routes = {
  board: "/api/board",
  live: (id: string): string => `/api/live?id=${encodeURIComponent(id)}`,
  post: (id: string, action: string): string => `/api/task/${encodeURIComponent(id)}/${action}`,
  shot: (id: string, path: string): string =>
    `/api/task/${encodeURIComponent(id)}/shot/${encodeURIComponent(path.slice(path.lastIndexOf("/") + 1))}`,
  task: (id: string): string => `/api/task/${encodeURIComponent(id)}`,
  usage: "/api/usage",
  version: "/version",
} as const;

export interface Payload {
  answers?: Record<string, string>;
  lessonId?: string;
  text?: string;
}

/** The request body for one action; actions without input send `{}`. */
export function bodyFor(action: ActionId, payload: Payload): Record<string, unknown> {
  switch (action) {
    case "lesson-approve": {
      return { lesson_id: payload.lessonId ?? "" };
    }
    case "send": {
      return { text: payload.text ?? "" };
    }
    case "spec-answers": {
      return { answers: payload.answers ?? {} };
    }
    default: {
      return {};
    }
  }
}
