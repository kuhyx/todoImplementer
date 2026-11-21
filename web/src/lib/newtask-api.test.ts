import { afterEach, describe, expect, it, vi } from "vitest";

import { MAX_IMAGES, ownTaskRequest, ownTaskResponse, postNewTask, uploadFile, uploadResponse } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";
import { contractValidator } from "@/test/contract-ajv";
import { makeCards } from "@/test/fixtures";
import { stubFetch } from "@/test/net";

const [card] = makeCards();
const REQUEST = { body: "see pic", images: [{ data_b64: "/9j/4AAQ" }], repo: "kuhyx/demo", title: "Fix it" };
const OK = { note: "abcd1234", ok: true, started: true, task: card };
const ID = "a".repeat(32);
const UPLOADED = { ok: true, upload: { id: ID, name: "Q3 ż.pdf", size: 3 } };

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
    expect(agree("requests", "new_task", ownTaskRequest, { title: "x" })).toEqual([true, true]);
    for (const bad of [{ ...REQUEST, repo: "demo" }, { ...REQUEST, title: "a\nb" }, { ...REQUEST, title: " " }, { ...REQUEST, images: [{}] }, { ...REQUEST, extra: 1 }]) {
      expect(agree("requests", "new_task", ownTaskRequest, bad)).toEqual([false, false]);
    }
    expect(agree("requests", "new_task", ownTaskRequest, { ...REQUEST, images: Array.from({ length: MAX_IMAGES + 1 }, () => ({ data_b64: "/9j/" })) })).toEqual([false, false]);
    expect(agree("requests", "new_task", ownTaskRequest, { ...REQUEST, files: [ID, "b".repeat(32)] })).toEqual([true, true]);
    for (const files of [["x"], [ID, ID]]) expect(agree("requests", "new_task", ownTaskRequest, { ...REQUEST, files })).toEqual([false, false]);
  });

  it("agrees on the upload answer", () => {
    expect(agree("response", undefined, uploadResponse, UPLOADED)).toEqual([true, true]);
    expect(agree("response", undefined, uploadResponse, { ok: true, upload: { ...UPLOADED.upload, id: "x" } })).toEqual([false, false]);
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

describe("uploadFile", () => {
  it("posts the raw file with its encoded name and the CSRF header, and resolves with the id", async () => {
    const stub = stubFetch({ [`POST ${routes.upload}`]: UPLOADED });
    const file = new File(["pdf"], "Q3 ż.pdf", { type: "application/pdf" });
    await expect(uploadFile(file, "tok")).resolves.toBe(ID);
    const init = stub.calls[0]?.init;
    expect(init?.body).toBe(file);
    expect(init?.headers).toEqual({ "Content-Type": "application/octet-stream", "X-Todoimpl-Name": "Q3%20%C5%BC.pdf", "X-Todoimpl-Token": "tok" });
  });

  it("rejects with the server's message or a bad shape", async () => {
    stubFetch({ [`POST ${routes.upload}`]: () => Response.json({ error: { code: "bad_request", message: "big.mov is over 100 MB" }, ok: false }, { status: 400 }) });
    await expect(uploadFile(new File(["x"], "big.mov"), "tok")).rejects.toMatchObject({ message: "big.mov is over 100 MB" });
    stubFetch({ [`POST ${routes.upload}`]: { ok: true } });
    await expect(uploadFile(new File(["x"], "a"), "tok")).rejects.toMatchObject({ code: "shape" });
  });
});
