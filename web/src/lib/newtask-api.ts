/** POST /api/upload and /api/new-task: Zod mirrors of contracts/requests.schema.json `new_task` and the response.schema.json answers. */
import { z } from "zod";

import { ApiError, readJson, send, shapeMessage } from "@/lib/http";
import { routes } from "@/lib/routes";
import { apiError, type TaskCard, taskCard } from "@/lib/schemas-common";

export const MAX_TITLE = 200;
export const MAX_BODY = 20_000;
export const MAX_IMAGES = 1000; // no real cap: the bytes are capped (T2426)
const MB = 1024 * 1024;
export const MAX_FILE = 100 * MB;
export const MAX_TOTAL = 500 * MB;
const FILE_ID = /^[0-9a-f]{32}$/v;
const areDistinct = (ids: readonly string[]): boolean => {
  const seen = new Set(ids);
  return seen.size === ids.length;
};
export const REPO = /^[\w.\-]+\/[\w.\-]+$/v;

export const ownTaskRequest = z.strictObject({
  body: z.string().max(MAX_BODY).optional(),
  files: z.array(z.string().regex(FILE_ID)).max(1000).refine((ids) => areDistinct(ids)).optional(),
  images: z.array(z.union([z.strictObject({ upload: z.string().regex(FILE_ID) }), z.strictObject({ data_b64: z.string().min(4) })])).max(MAX_IMAGES).optional(),
  repo: z.string().regex(REPO).optional(),
  title: z.string().max(MAX_TITLE).regex(/^[^\r\n]*$/v).refine((title) => title.trim() !== ""),
});

export const ownTaskResponse = z.union([
  z.strictObject({ note: z.string().regex(/^[A-Za-z0-9]{8}$/v), ok: z.literal(true), started: z.boolean(), task: taskCard.optional() }),
  z.strictObject({ error: apiError, ok: z.literal(false) }),
]);

export const uploadResponse = z.union([
  z.strictObject({ ok: z.literal(true), upload: z.strictObject({ id: z.string().regex(FILE_ID), name: z.string().min(1).max(200), size: z.int().min(0) }) }),
  z.strictObject({ error: apiError, ok: z.literal(false) }),
]);

const IMAGE_REF = /\[Image #\d+\]/v;
const IMAGE_REFS = /\[Image #\d+\]/gv;

/** A line's text with its `[Image #N]` refs taken out (spaces folded); a line with none is only trimmed. */
function cleanLine(line: string): string {
  return IMAGE_REF.test(line) ? line.replaceAll(IMAGE_REFS, " ").split(/\s+/v).filter(Boolean).join(" ") : line.trim();
}

/**
 * The one description box as (title, body), the same rule as the server's `newtask/titles.py` and the app's
 * `splitNote` (T2481): the title is the first line of real text with its image refs out, cut to MAX_TITLE; a
 * note with no text keeps its first line (`[Image #1]`). A skipped or cleaned ref line, or a cut, keeps the
 * whole text as the body, so no ref is lost.
 */
export function splitNote(text: string): { body: string; title: string } {
  const all = text.trim();
  const lines = all.split(/\r?\n/v);
  const found = lines.findIndex((line) => cleanLine(line) !== "");
  const at = Math.max(found, 0);
  const title = found === -1 ? (lines[0] ?? "").trim() : cleanLine(lines[at] ?? "");
  const isLossy = found !== -1 && (title !== (lines[at] ?? "").trim() || lines.slice(0, at).some((line) => line.trim() !== ""));
  if (title.length > MAX_TITLE) return { body: all, title: title.slice(0, MAX_TITLE).trim() };
  return { body: isLossy ? all : lines.slice(at + 1).join("\n").trim(), title };
}

export type OwnTaskRequest = z.infer<typeof ownTaskRequest>;
export interface Created {
  note: string;
  started: boolean;
  task?: TaskCard;
}

/** Resolves with the repo card (started or already at work); rejects with the server's own message. */
export async function postNewTask(request: OwnTaskRequest, csrf: string): Promise<Created> {
  const url = routes.ownTask;
  const response = await send(url, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = ownTaskResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  const { note, started, task } = parsed.data;
  return { note, started, ...(task !== undefined && { task }) };
}

/** Streams one file (any type, unchanged bytes) to the staging dir; resolves with the id new_task `files` takes. */
export async function uploadFile(file: File, csrf: string): Promise<string> {
  const url = routes.upload;
  const response = await send(url, {
    body: file,
    headers: { "Content-Type": "application/octet-stream", "X-Todoimpl-Name": encodeURIComponent(file.name), "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = uploadResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  return parsed.data.upload.id;
}
