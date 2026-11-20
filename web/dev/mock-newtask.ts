/** Mock of POST /api/new-task (http/newtask.py `check`): repo is optional, title is one non-blank line; answers like the server. GET /mock/new-tasks lists what was accepted. */
import type { IncomingMessage, ServerResponse } from "node:http";

import { text } from "node:stream/consumers";

const REPO = /^[\w.\-]+\/[\w.\-]+$/v;
const made: unknown[] = [];

function refuse(res: ServerResponse, status: number, code: string, message: string): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { code, message }, ok: false }));
}

/** True when `path` was one of the two routes and the answer is sent. */
export async function hasServedNewTask(request: IncomingMessage, res: ServerResponse, path: string, token: string): Promise<boolean> {
  if (path === "/mock/new-tasks") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(made));
    return true;
  }
  if (path !== "/api/new-task" || request.method !== "POST") return false;
  const raw = await text(request);
  const origin = request.headers.origin;
  if (request.headers["x-todoimpl-token"] !== token || (origin !== undefined && origin !== `http://${request.headers.host ?? ""}`)) {
    refuse(res, 403, "forbidden", "Bad token or origin.");
    return true;
  }
  const body = JSON.parse(raw) as { repo?: unknown; title?: unknown };
  if (body.repo !== undefined && !(typeof body.repo === "string" && REPO.test(body.repo))) refuse(res, 400, "bad_request", "repo must look like owner/name");
  else if (typeof body.title !== "string" || body.title.trim() === "") refuse(res, 400, "bad_request", "title must be 1..200 characters on one line");
  else {
    made.push(body);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ note: "abcd1234", ok: true, started: false }));
  }
  return true;
}
