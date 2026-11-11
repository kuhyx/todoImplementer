import { afterEach, describe, expect, it, vi } from "vitest";

import { result, sessionList } from "#fixtures/fixture-sessions";
import { stubFetch } from "#fixtures/net";
import { ApiError } from "@/lib/http";
import { actionUrl, loadSessions, postSessions } from "@/sessions/api";

afterEach(() => { vi.unstubAllGlobals(); });

const post = (): Promise<unknown> => postSessions("mark", { ids: ["x"], mark: "done" }, "tok");

describe("loadSessions", () => {
  it("parses the list", async () => {
    stubFetch({ "GET /api/sessions": sessionList() });
    const list = await loadSessions();
    expect(list.sessions).toHaveLength(8);
  });

  it("rejects a shape the contract does not allow", async () => {
    stubFetch({ "GET /api/sessions": { ...sessionList(), extra: 1 } });
    await expect(loadSessions()).rejects.toThrow(/unexpected shape/v);
  });
});

describe("postSessions", () => {
  it("sends the body with the CSRF header and parses the result", async () => {
    const stub = stubFetch({ "POST /api/sessions/mark": result({ summary: "marked" }) });
    expect((await post() as { summary: string }).summary).toBe("marked");
    const init = stub.calls[0]?.init;
    expect(init?.headers).toEqual({ "Content-Type": "application/json", "X-Todoimpl-Token": "tok" });
    expect(JSON.parse(init?.body as string)).toEqual({ ids: ["x"], mark: "done" });
    expect(actionUrl("delete")).toBe("/api/sessions/delete");
  });

  it("resolves a refusal: the guard working is an answer, not an error", async () => {
    stubFetch({ "POST /api/sessions/mark": result({ ok: false, refused: true }) });
    expect(await post()).toMatchObject({ ok: false, refused: true });
  });

  it("rejects with the server's own message on a 403", async () => {
    const body = { error: { code: "forbidden", message: "bad token" }, ok: false };
    stubFetch({ "POST /api/sessions/mark": () => Response.json(body, { status: 403 }) });
    await expect(post()).rejects.toMatchObject({ code: "forbidden", message: "bad token", status: 403 });
  });

  it("rejects an error body of another shape with the status", async () => {
    stubFetch({ "POST /api/sessions/mark": () => Response.json({ nope: 1 }, { status: 500 }) });
    await expect(post()).rejects.toMatchObject({ code: "http", message: "/api/sessions/mark: HTTP 500" });
  });

  it("rejects a 200 that is not the result shape", async () => {
    stubFetch({ "POST /api/sessions/mark": { ok: true } });
    await expect(post()).rejects.toMatchObject({ code: "shape" });
  });

  it("rejects when the server cannot be reached", async () => {
    stubFetch({ "POST /api/sessions/mark": new Error("down") });
    await expect(post()).rejects.toBeInstanceOf(ApiError);
  });
});
