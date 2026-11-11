import { afterEach, describe, expect, it, vi } from "vitest";

import { ownTaskRequest, ownTaskResponse, postNewTask } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";
import { contractValidator } from "@/test/contract-ajv";
import { makeCards } from "@/test/fixtures";
import { stubFetch } from "@/test/net";

const [card] = makeCards();
const REQUEST = { body: "see pic", images: [{ data_b64: "/9j/4AAQ" }], repo: "kuhyx/demo", title: "Fix it" };
const OK = { note: "abcd1234", ok: true, started: true, task: card };

function agree(file: string, def: string | undefined, schema: { safeParse: (v: unknown) => { success: boolean } }, value: unknown): boolean[] {
  return [contractValidator(file, def)(value), schema.safeParse(value).success];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("new task contract mirror", () => {
  it("agrees on good and bad requests", () => {
    expect(agree("requests", "new_task", ownTaskRequest, REQUEST)).toEqual([true, true]);
    expect(agree("requests", "new_task", ownTaskRequest, { repo: "kuhyx/demo", title: "x" })).toEqual([true, true]);
    for (const bad of [{ ...REQUEST, repo: "demo" }, { ...REQUEST, title: "a\nb" }, { ...REQUEST, title: " " }, { ...REQUEST, images: [{}] }, { ...REQUEST, extra: 1 }]) {
      expect(agree("requests", "new_task", ownTaskRequest, bad)).toEqual([false, false]);
    }
    expect(agree("requests", "new_task", ownTaskRequest, { ...REQUEST, images: Array.from({ length: 9 }, () => ({ data_b64: "/9j/" })) })).toEqual([false, false]);
  });

  it("agrees on the answers", () => {
    expect(agree("response", undefined, ownTaskResponse, OK)).toEqual([true, true]);
    expect(agree("response", undefined, ownTaskResponse, { ...OK, started: false })).toEqual([true, true]);
    expect(agree("response", undefined, ownTaskResponse, { error: { code: "conflict", message: "twin" }, ok: false })).toEqual([true, true]);
    expect(agree("response", undefined, ownTaskResponse, { ...OK, note: "abc" })).toEqual([false, false]);
  });
});

describe("postNewTask", () => {
  it("posts the body with the CSRF header and resolves with the card and whether it started", async () => {
    const stub = stubFetch({ [`POST ${routes.ownTask}`]: OK });
    await expect(postNewTask(REQUEST, "tok")).resolves.toEqual({ note: "abcd1234", started: true, task: card });
    const init = stub.calls[0]?.init;
    expect(init?.headers).toEqual({ "Content-Type": "application/json", "X-Todoimpl-Token": "tok" });
    expect(JSON.parse(init?.body as string)).toEqual(REQUEST);
  });

  it("rejects with the server's own message", async () => {
    stubFetch({ [`POST ${routes.ownTask}`]: () => Response.json({ error: { code: "conflict", message: "twin title" }, ok: false }, { status: 409 }) });
    await expect(postNewTask(REQUEST, "tok")).rejects.toMatchObject({ code: "conflict", message: "twin title", status: 409 });
  });

  it("rejects an unexpected shape", async () => {
    stubFetch({ [`POST ${routes.ownTask}`]: { ok: true } });
    await expect(postNewTask(REQUEST, "tok")).rejects.toMatchObject({ code: "shape" });
  });
});
