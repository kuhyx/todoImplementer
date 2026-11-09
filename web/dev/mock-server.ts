/**
 * Dev mock of the todoImplementer server: serves web/dist with the CSRF and
 * build placeholders stamped, plus fixture /API, /version and SSE. Enforces the
 * real server's rules (token + same-origin on POST, CSP default-src 'self') so
 * a viewport run surfaces violations. Run: `pnpm build && PORT=4399 node dev/mock-server.ts`.
 */
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { extname, join, normalize } from "node:path";

import { ASK_IDS, askCards, askDetail, FREE_ID, freeDetail } from "#fixtures/fixture-ask";
import { makeDetail, makeUsage } from "#fixtures/fixture-detail";
import { preset } from "#fixtures/fixture-presets";
import { makeBoard, makeCards, NOW } from "#fixtures/fixtures";

const PORT = Number(process.env.PORT ?? 4399);
const BUILD = process.env.MOCK_BUILD ?? "mock0001";
const DIST = process.env.MOCK_DIST ?? join(import.meta.dirname, "..", "dist");
const TOKEN = randomUUID();
const TYPES: Record<string, string> = { ".css": "text/css", ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".svg": "image/svg+xml" };
const TIME_KEYS = new Set(["at", "ended", "generated_at", "resets_at", "resumes_at", "started", "until", "updated"]);
const offset = Math.floor(Date.now() / 1000) - NOW;
const cards = [...makeCards(), ...askCards()].map((card) => (card.status === "working" && card.repo === "gatelock" ? { ...card, route: "credits" as const } : card));
let isCreditsOn = true;
const creditsNow = (): unknown => ({ enabled: isCreditsOn, state: isCreditsOn ? "ready" : "off", text: isCreditsOn ? "Free API credits take over while the plan limit is active." : "Runs wait for the plan limit to end." });
const streams = new Map<string, Set<ServerResponse>>();

function shift(value: unknown, key = ""): unknown {
  if (typeof value === "number") return TIME_KEYS.has(key) ? value + offset : value;
  if (Array.isArray(value)) return value.map((item) => shift(item, key));
  return value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shift(v, k)])) : value;
}

function json(res: ServerResponse, body: unknown, status = 200): void {
  res.writeHead(status, { "Cache-Control": "no-store", "Content-Type": "application/json" });
  res.end(JSON.stringify(shift(body)));
}

function emit(id: string, type: string, data: unknown): void {
  const frame = `event: ${type}\ndata: ${JSON.stringify(shift(data))}\n\n`;
  const open = streams.get(id);
  if (open === undefined) return;
  for (const res of open) res.write(frame);
}

function stageEvent(id: string): unknown {
  const card = cards.find((c) => c.id === id);
  if (card === undefined || card.stage === null) return null;
  const { actions, column, current, needs, stage, status } = card;
  return { actions, column, current, needs, stage, status, type: "stage" };
}

const NEXT: Record<string, "backlog" | "cancelled" | "done" | "working"> = { cancel: "cancelled", ship: "done", "spec-answers": "working", "spec-ok": "working", start: "working" };

function hasTask(id: string, action: string, body: { text?: string }): boolean {
  const card = cards.find((c) => c.id === id);
  if (card === undefined) return false;
  const next = NEXT[action];
  if (next !== undefined) Object.assign(card, preset(next, card.repo !== null), { updated: NOW });
  if (action === "send") emit(id, "activity", { at: NOW, kind: "user", seq: Date.now() % 1_000_000, text: body.text ?? "", tool: null, type: "activity" });
  const event = stageEvent(id);
  if (event !== null) emit(id, "stage", event);
  return true;
}

async function setCredits(request: IncomingMessage, res: ServerResponse): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  const origin = request.headers.origin;
  if (request.headers["x-todoimpl-token"] !== TOKEN || (origin !== undefined && origin !== `http://${request.headers.host ?? ""}`)) {
    json(res, { error: { code: "forbidden", message: "Bad token or origin." }, ok: false }, 403); return;
  }
  const body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as { enabled?: unknown };
  if (typeof body.enabled !== "boolean") { json(res, { error: { code: "bad_request", message: "enabled must be true or false." }, ok: false }, 400); return; }
  isCreditsOn = body.enabled;
  json(res, { credits: creditsNow(), ok: true });
}

async function post(request: IncomingMessage, res: ServerResponse, id: string, action: string): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  const origin = request.headers.origin;
  if (request.headers["x-todoimpl-token"] !== TOKEN || (origin !== undefined && origin !== `http://${request.headers.host ?? ""}`)) {
    json(res, { error: { code: "forbidden", message: "Bad token or origin." }, ok: false }, 403); return;
  }
  const card = cards.find((c) => c.id === id);
  const found = card?.actions.find((a) => a.id === action);
  if (card === undefined || found === undefined) { json(res, { error: { code: "not_found", message: "No such task or action." }, ok: false }, 404); return; }
  if (!found.enabled) { json(res, { error: { code: "disabled", message: found.reason ?? "Not allowed." }, ok: false }, 409); return; }
  if (action === "ship") await new Promise((resolve) => setTimeout(resolve, 1500));
  hasTask(id, action, JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as { text?: string });
  json(res, { ok: true, task: card });
}

function live(request: IncomingMessage, res: ServerResponse, id: string): void {
  res.writeHead(200, { "Cache-Control": "no-store", "Content-Type": "text/event-stream" });
  streams.set(id, (streams.get(id) ?? new Set()).add(res));
  const snapshot = stageEvent(id);
  if (snapshot !== null) res.write(`event: stage\ndata: ${JSON.stringify(shift(snapshot))}\n\n`);
  let seq = 0;
  const timer = setInterval(() => {
    seq += 1;
    emit(id, "activity", { at: NOW, kind: seq % 3 === 0 ? "tool" : "text", seq, text: `Step ${String(seq)}: working on ${id}`, tool: seq % 3 === 0 ? "Bash" : null, type: "activity" });
  }, 2000);
  request.on("close", () => {
    clearInterval(timer);
    streams.get(id)?.delete(res);
  });
}

async function serveStatic(res: ServerResponse, path: string): Promise<void> {
  const file = normalize(path === "/" ? "/index.html" : path).replace(/^(\.\.[\/\\])+/v, "");
  try {
    let data = await readFile(join(DIST, file));
    if (file === "/index.html") {
      data = Buffer.from(data.toString("utf8").replace("__TODOIMPL_CSRF__", () => TOKEN).replace("__TODOIMPL_BUILD__", () => BUILD));
    }
    res.writeHead(200, { "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'", "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
}

const SHOT =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400"><rect width="640" height="400" fill="#38312e"/><text x="32" y="64" fill="#eceae9" font-size="32">mock screenshot</text></svg>';

function detailFor(card: (typeof cards)[number]): unknown {
  if (card.status !== "needs_you" || !ASK_IDS.includes(card.id)) return makeDetail(card);
  return { ...(card.id === FREE_ID ? freeDetail() : askDetail(card.id)), card };
}

async function route(request: IncomingMessage, res: ServerResponse): Promise<void> {
  const target = request.url ?? "/";
  const [path = "/", query = ""] = target.split("?", 2);
  const parameters = new URLSearchParams(query);
  const [, api, kind, id, action] = path.split("/", 5);
  if (path === "/version") { json(res, { build: BUILD, version: "0.1.0" }); return; }
  if (path === "/api/board") { const board = makeBoard(cards); json(res, { ...board, build: BUILD, limit: { ...board.limit, credits: creditsNow() } }); return; }
  if (path === "/api/settings/credits-fallback" && request.method === "POST") { await setCredits(request, res); return; }
  if (path === "/api/usage") { json(res, makeUsage()); return; }
  if (path === "/api/live") { live(request, res, parameters.get("id") ?? ""); return; }
  if (api !== "api" || kind !== "task" || id === undefined) {
    await serveStatic(res, path);
    return;
  }
  if (action === "shot") {
    res.writeHead(200, { "Content-Type": "image/svg+xml" });
    res.end(SHOT);
    return;
  }
  if (action !== undefined && request.method === "POST") {
    await post(request, res, id, action);
    return;
  }
  const card = cards.find((c) => c.id === id);
  if (card === undefined) json(res, { error: { code: "not_found", message: "No such task." }, ok: false }, 404);
  else json(res, detailFor(card));
}

createServer(async (request, res) => {
  await route(request, res);
}).listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`mock on 127.0.0.1:${String(PORT)} build ${BUILD}\n`);
});
