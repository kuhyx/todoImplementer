import { describe, expect, it } from "vitest";

import { hashContext, memoryContext } from "@/usage/context";
import { EMPTY_TABLE } from "@/usage/table-model";

describe("hashContext", () => {
  it("reads filters and table state from the live hash and writes without pushing history", () => {
    globalThis.location.hash = "#/sessions?cwd=a&t.sessions.q=hi";
    const before = globalThis.history.length;
    const context = hashContext();
    expect(context.filters().toString()).toBe("cwd=a");
    expect(context.read("sessions").q).toBe("hi");
    expect(context.href("s", "k")).toBe("#/s/k?cwd=a");
    context.write("sessions", { ...EMPTY_TABLE, q: "bye" });
    expect(globalThis.location.hash).toBe("#/sessions?cwd=a&t.sessions.q=bye");
    context.write("sessions", EMPTY_TABLE);
    expect(globalThis.location.hash).toBe("#/sessions?cwd=a");
    expect(globalThis.history).toHaveLength(before);
  });

  it("falls back to the overview path when the hash is empty", () => {
    globalThis.history.replaceState(null, "", "/usage/");
    hashContext().write("x", { ...EMPTY_TABLE, q: "a" });
    expect(globalThis.location.hash).toBe("#/overview?t.x.q=a");
  });
});

describe("hashContext without other state", () => {
  it("leaves a bare route when the table is reset", () => {
    globalThis.location.hash = "#/sessions";
    hashContext().write("sessions", { ...EMPTY_TABLE, q: "a" });
    hashContext().write("sessions", EMPTY_TABLE);
    expect(globalThis.location.hash).toBe("#/sessions");
  });
});

describe("memoryContext", () => {
  it("mirrors the same contract in memory", () => {
    const context = memoryContext("cwd=a");
    context.write("t", { ...EMPTY_TABLE, q: "z" });
    expect(context.hash()).toBe("cwd=a&t.t.q=z");
    expect(context.read("t").q).toBe("z");
    expect(context.filters().get("cwd")).toBe("a");
    expect(context.href("f", "/p")).toBe("#/f/%2Fp?cwd=a");
  });
});
