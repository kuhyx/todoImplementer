import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, errorText, getJson, postAction } from "@/lib/http";
import { bodyFor, routes } from "@/lib/routes";
import { version } from "@/lib/schemas";
import { makeCards } from "@/test/fixtures";
import { stubFetch } from "@/test/net";

afterEach(() => {
  vi.unstubAllGlobals();
});

const catchError = async (promise: Promise<unknown>): Promise<ApiError> => {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
  }
  throw new Error("expected an ApiError");
};

describe("getJson", () => {
  it("parses a good body", async () => {
    stubFetch({ "GET /version": { build: "abc", version: "1" } });
    expect(await getJson("/version", version)).toEqual({ build: "abc", version: "1" });
  });

  it("names the url on HTTP errors, bad JSON, bad shape and network failure", async () => {
    stubFetch({ "GET /a": new Response("nope", { status: 500 }), "GET /b": new Response("<html>", { status: 200 }), "GET /c": { build: 1 }, "GET /d": new Error("down") });
    const http = await catchError(getJson("/a", version));
    expect([http.code, http.status, http.message]).toEqual(["http", 500, "/a: HTTP 500"]);
    const notJson = await catchError(getJson("/b", version));
    expect(notJson.code).toBe("not_json");
    const shape = await catchError(getJson("/c", version));
    expect([shape.code, shape.message]).toEqual(["shape", "/c: the server sent an unexpected shape at build"]);
    const offline = await catchError(getJson("/d", version));
    expect(offline.message).toBe("/d: cannot reach the server");
  });

  it("reports a root-level shape problem", async () => {
    stubFetch({ "GET /e": [] });
    const root = await catchError(getJson("/e", version));
    expect(root.message).toContain("at root");
  });
});

describe("postAction", () => {
  const [card] = makeCards();

  it("sends the token and the action body and returns the card", async () => {
    const stub = stubFetch({ "POST /api/task/01a1b2c3-0/send": { ok: true, task: card } });
    const task = await postAction("01a1b2c3-0", "send", { text: "hi" }, "tok");
    expect(task.id).toBe("01a1b2c3-0");
    const call = stub.calls[0];
    expect(call?.init?.body).toBe('{"text":"hi"}');
    expect(call?.init?.headers).toEqual({ "Content-Type": "application/json", "X-Todoimpl-Token": "tok" });
  });

  it("rejects with the server's own message", async () => {
    stubFetch({ "POST /api/task/01a1b2c3-0/ship": () => Response.json({ error: { code: "disabled", message: "No slot" }, ok: false }, { status: 409 }) });
    const error = await catchError(postAction("01a1b2c3-0", "ship", {}, "tok"));
    expect([error.message, error.code, error.status]).toEqual(["No slot", "disabled", 409]);
  });

  it("rejects an answer of the wrong shape", async () => {
    stubFetch({ "POST /api/task/01a1b2c3-0/ship": { ok: "yes" } });
    const bad = await catchError(postAction("01a1b2c3-0", "ship", {}, "t"));
    expect(bad.code).toBe("shape");
  });
});

describe("errorText", () => {
  it("uses an Error's message, else a generic one", () => {
    expect(errorText(new Error("boom"))).toBe("boom");
    expect(errorText("boom")).toBe("unknown error");
  });
});

describe("routes", () => {
  it("builds urls and request bodies", () => {
    expect(routes.live("a b")).toBe("/api/live?id=a%20b");
    expect(routes.task("x")).toBe("/api/task/x");
    expect(bodyFor("spec-answers", { answers: { Q1: "a" } })).toEqual({ answers: { Q1: "a" } });
    expect(bodyFor("spec-answers", {})).toEqual({ answers: {} });
    expect(bodyFor("send", { text: "t" })).toEqual({ text: "t" });
    expect(bodyFor("send", {})).toEqual({ text: "" });
    expect(bodyFor("lesson-approve", { lessonId: "l1" })).toEqual({ lesson_id: "l1" });
    expect(bodyFor("lesson-approve", {})).toEqual({ lesson_id: "" });
    expect(bodyFor("ship", { text: "ignored" })).toEqual({});
  });
});
