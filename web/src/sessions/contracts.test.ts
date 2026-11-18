/** The JSON Schema and the Zod mirror agree on the shared fixture and on the bodies the page sends. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { contractValidator } from "#fixtures/contract-ajv";
import { result, sessionList } from "#fixtures/fixture-sessions";
import { sessionList as listSchema, mutationResult } from "@/sessions/schemas";

const shared: unknown = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "..", "tests", "fixtures", "sessions.json"), "utf8"));
const ID = "11111111-2222-4333-8444-555555555555";

describe("contracts/sessions.schema.json", () => {
  it("accepts the shared fixture in both validators", () => {
    expect(contractValidator("sessions")(shared)).toBe(true);
    expect(listSchema.safeParse(shared).success).toBe(true);
  });

  it("accepts what the page's own fixtures carry", () => {
    expect(contractValidator("sessions")(sessionList())).toBe(true);
    expect(contractValidator("sessions", "result")(result())).toBe(true);
    expect(mutationResult.safeParse(result()).success).toBe(true);
  });

  it("rejects the same bad list in both validators", () => {
    const bad = { ...(shared as object), sessions: [{ id: "not-a-uuid" }] };
    expect(contractValidator("sessions")(bad)).toBe(false);
    expect(listSchema.safeParse(bad).success).toBe(false);
  });

  it.each([
    ["resume_body", { id: ID }, true],
    ["resume_body", { ids: [ID, ID, ID, ID, ID] }, true],
    ["resume_body", { ids: [ID, ID, ID, ID, ID, ID] }, false],
    ["resume_body", {}, false],
    ["mark_body", { ids: [ID], mark: null }, true],
    ["mark_body", { id: ID, mark: "done" }, true],
    ["mark_body", { id: ID }, false],
    ["delete_body", { id: ID, ids: [ID] }, false],
    ["delete_body", { ids: [ID] }, true],
    ["handoff_body", { id: ID }, true],
    ["handoff_body", { ids: [ID], repos: { [ID]: "kuhyx/demo" } }, true],
    ["handoff_body", { ids: [ID, ID, ID, ID, ID, ID] }, false],
    ["handoff_body", { id: ID, repos: { [ID]: "no slash" } }, false],
  ])("%s %j is %s", (def, body, valid) => {
    expect(contractValidator("sessions", def)(body)).toBe(valid);
  });
});
