/** Every URL and POST body shape in one place (contracts/requests.schema.json). */
import type { ActionId } from "@/lib/schemas-common";

export const routes = {
  board: "/api/board",
  creditsFallback: "/api/settings/credits-fallback",
  issues: (id: string): string => `/api/task/${encodeURIComponent(id)}/issues`,
  /** The readable issue log page (web/src/issues); `issues` above is its raw ndjson. */
  issuesPage: (id: string): string => `/issues#task=${encodeURIComponent(id)}`,
  live: (id: string): string => `/api/live?id=${encodeURIComponent(id)}`,
  ownTask: "/api/new-task",
  post: (id: string, action: string): string => `/api/task/${encodeURIComponent(id)}/${action}`,
  /** `path` is run-dir relative ("shots/live2/v1.png"); the server serves it from under <run>/shots. */
  shot: (id: string, path: string): string =>
    `/api/task/${encodeURIComponent(id)}/shot/${path.replace(/^shots\//, "").split("/").map((part) => encodeURIComponent(part)).join("/")}`,
  task: (id: string): string => `/api/task/${encodeURIComponent(id)}`,
  umbrella: (id: string): string => `/api/umbrella/${encodeURIComponent(id)}`,
  upload: "/api/upload",
  usage: "/api/usage",
  version: "/version",
  workerLog: (id: string, child: string): string => `/api/umbrella/${encodeURIComponent(id)}/log/${encodeURIComponent(child)}`,
} as const;

export interface Payload {
  answers?: Record<string, string>;
  autoShip?: boolean | undefined;
  /** Send's numbered images: `[Image #N]` is item N (contracts/requests.schema.json image_ref). */
  images?: { upload: string }[];
  lessonId?: string;
  model?: string | undefined;
  text?: string;
}

/** The request body for one action; actions without input send `{}`. */
export function bodyFor(action: ActionId, payload: Payload): Record<string, unknown> {
  switch (action) {
    case "lesson-approve": {
      return { lesson_id: payload.lessonId ?? "" };
    }
    case "model": {
      return { model: payload.model ?? "default" };
    }
    case "send": {
      const images = payload.images ?? [];
      return { ...(images.length > 0 && { images }), text: payload.text ?? "" };
    }
    case "spec-answers": {
      return { answers: payload.answers ?? {} };
    }
    case "start": {
      return payload.autoShip === undefined ? {} : { auto_ship: payload.autoShip };
    }
    default: {
      return {};
    }
  }
}
