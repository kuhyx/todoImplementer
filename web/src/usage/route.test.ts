import { describe, expect, it } from "vitest";

import { formatRoute, linkTo, parseRoute, tabFor, VIEWS, withQuery } from "@/usage/route";

describe("parseRoute", () => {
  it("defaults to the overview", () => {
    expect(parseRoute("")).toMatchObject({ arg: "", view: "overview" });
    expect(parseRoute("#/nonsense")).toMatchObject({ view: "overview" });
    expect(parseRoute("#/more")).toMatchObject({ arg: "", view: "more" });
  });

  it("reads tabs, query, sessions, files and panels", () => {
    expect(parseRoute("#/sessions?cwd=a").parameters.get("cwd")).toBe("a");
    expect(parseRoute("#/s/abc-123")).toMatchObject({ arg: "abc-123", view: "s" });
    expect(parseRoute("#/f/%2Fhome%2Fx%2Fa.md")).toMatchObject({ arg: "/home/x/a.md", view: "f" });
    expect(parseRoute("#/more/hooks")).toMatchObject({ arg: "hooks", view: "more" });
    expect(parseRoute("#/s")).toMatchObject({ arg: "", view: "s" });
  });
});

describe("formatRoute", () => {
  it("round-trips every shape", () => {
    for (const hash of ["#/overview", "#/sessions?cwd=a", "#/s/abc", "#/f/%2Fa%2Fb.md", "#/more/hooks?scope=main"]) {
      expect(formatRoute(parseRoute(hash))).toBe(hash);
    }
  });

  it("links keep global filters but drop table state", () => {
    expect(linkTo("s", "k1", new URLSearchParams("cwd=a&t.sessions.q=x"))).toBe("#/s/k1?cwd=a");
    expect(linkTo("sessions", "", new URLSearchParams())).toBe("#/sessions");
    expect(withQuery("p", "a=1")).toBe("p?a=1");
  });

  it("maps drill-downs to their tab", () => {
    expect(VIEWS.map((view) => view.id)).toContain("items");
    expect([tabFor("s"), tabFor("f"), tabFor("ab")]).toEqual(["sessions", "context", "ab"]);
  });
});
