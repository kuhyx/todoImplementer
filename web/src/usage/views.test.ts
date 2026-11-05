import { afterEach, describe, expect, it, vi } from "vitest";

import { memoryContext } from "@/usage/context";
import { fakeFetch, fixtures } from "@/usage/fixtures/load";
import { abView } from "@/usage/view-ab";
import { anomaliesView } from "@/usage/view-anomalies";
import { contextView } from "@/usage/view-context";
import { efficiencyView } from "@/usage/view-efficiency";
import { fileView } from "@/usage/view-file";
import { itemsView } from "@/usage/view-items";
import { leversView } from "@/usage/view-levers";
import { genericView, moreIndexView } from "@/usage/view-more";
import { overviewView } from "@/usage/view-overview";
import { sessionView } from "@/usage/view-session";
import { sessionsView } from "@/usage/view-sessions";

const { signal } = new AbortController();
const context = (): ReturnType<typeof memoryContext> => memoryContext("cwd=%2Fhome%2Fkuhy");
const use = (routes: Record<string, unknown> = {}): void => {
  vi.stubGlobal("fetch", vi.fn(fakeFetch(routes)));
};
const text = (view: HTMLElement): string => view.textContent;
const clean = (view: HTMLElement): void => {
  expect(text(view)).not.toMatch(/\[object Object\]|undefined|NaN/v);
};
const clone = <T>(value: T): T => structuredClone(value);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("overview", () => {
  it("shows tiles, eight charts and the daily table from real data", async () => {
    use();
    const view = await overviewView(context(), signal);
    expect(view.querySelectorAll(".tile")).toHaveLength(6);
    expect(view.querySelectorAll(".chart svg")).toHaveLength(8);
    expect(view.querySelector("usage-table")).not.toBeNull();
    expect(text(view)).toContain("$173");
    clean(view);
  });
});

describe("sessions", () => {
  it("lists every session with a link to its detail and short model names", async () => {
    use();
    const view = await sessionsView(context(), signal);
    expect(view.querySelectorAll("tbody tr")).toHaveLength(42);
    expect(view.querySelector("tbody a")?.getAttribute("href")).toMatch(/^#\/s\/[\w\-]+\?cwd=/v);
    expect(text(view)).toContain("opus-5-5");
    clean(view);
  });

  it("shows one session with prompts, tools and subagents", async () => {
    use();
    const view = await sessionView(context(), signal, "k");
    expect(view.querySelector(".crumbs a")?.getAttribute("href")).toBe("#/sessions?cwd=%2Fhome%2Fkuhy");
    expect(view.querySelectorAll("usage-table")).toHaveLength(3);
    expect(view.querySelectorAll(".chart")).toHaveLength(1);
    clean(view);
  });

  it("copes with a session that has no cwd or tag", async () => {
    const data = clone(fixtures.session);
    Object.assign(data.session, { cwd: null, final_tag: null });
    use({ session: data });
    expect(text(await sessionView(context(), signal, "k"))).toContain("— · ");
  });
});

describe("context files", () => {
  it("lists files, counts the ones over budget and links to a file", async () => {
    use();
    const view = await contextView(context(), signal);
    expect(view.querySelector(".banner")?.getAttribute("data-level")).toBe("red");
    expect(view.querySelector("tbody a")?.getAttribute("href")).toMatch(/^#\/f\//v);
    expect(view.querySelectorAll("tbody tr")).toHaveLength(22);
    clean(view);
  });

  it("says so when every file is inside its budget", async () => {
    const data = clone(fixtures.context);
    for (const file of data.files) Object.assign(file, { breaches: [], status: "ok" });
    use({ "/api/tokens/panel/context": data });
    expect(text(await contextView(context(), signal))).toContain("inside its budget");
  });

  it("shows one file with breaches, history, git log and content", async () => {
    use();
    const path = fixtures.context.files[0]?.path ?? "";
    const view = await fileView(context(), signal, path);
    expect(view.querySelectorAll(".tile")).toHaveLength(4);
    expect(view.querySelector(".chart svg")).not.toBeNull();
    expect(view.querySelector("pre")?.textContent.length).toBeGreaterThan(10);
    expect(view.querySelectorAll(".log li").length).toBeGreaterThan(0);
    clean(view);
  });

  it("still shows content for a file the panel does not list, and an unreadable one", async () => {
    use({ "/api/tokens/context-file": { ...fixtures.contextFile, content: null } });
    const view = await fileView(context(), signal, "/not/listed.md");
    expect(view.querySelector(".tile")).toBeNull();
    expect(view.querySelector("pre")?.textContent).toBe("(not readable)");
  });

  it("draws no history chart for a file with one version and shows an ok banner", async () => {
    const data = clone(fixtures.context);
    const file = data.files[0];
    Object.assign(file ?? {}, { history: [], status: "ok" });
    use({ "/api/tokens/panel/context": data });
    const view = await fileView(context(), signal, file?.path ?? "");
    expect(view.querySelector(".chart")).toBeNull();
    expect(view.querySelector(".banner")?.getAttribute("data-level")).toBe("green");
  });
});

describe("levers, anomalies, A/B, efficiency", () => {
  it("levers: a chart per metric (daily when there is a series) and the table", async () => {
    use();
    const view = await leversView(context(), signal);
    expect(view.querySelectorAll(".chart")).toHaveLength(Object.keys(fixtures.levers.series).length);
    expect(view.querySelectorAll("usage-table tbody tr")).toHaveLength(14);
    clean(view);
  });

  it("anomalies: banner, tiles, charts and four tables", async () => {
    use();
    const view = await anomaliesView(context(), signal);
    expect(view.querySelectorAll("usage-table")).toHaveLength(4);
    expect(view.querySelectorAll(".chart")).toHaveLength(2);
    expect(view.querySelector(".banner")?.getAttribute("data-level")).toBe("red");
    clean(view);
  });

  it("anomalies: a green banner when nothing spiked", async () => {
    const data = clone(fixtures.anomalies);
    Object.assign(data.totals, { loops: 0, spikes: 0 });
    use({ "/api/tokens/panel/anomalies": data });
    const view = await anomaliesView(context(), signal);
    expect(view.querySelector(".banner")?.getAttribute("data-level")).toBe("green");
  });

  it("A/B: both experiments with intervals and the metrics table", async () => {
    use();
    const view = await abView(context(), signal);
    expect(view.querySelectorAll(".chart")).toHaveLength(2);
    expect(view.querySelectorAll("usage-table")).toHaveLength(2);
    expect(text(view)).toContain("unjoined");
    clean(view);
  });

  it("A/B: no build experiment, no unjoined count, no metrics", async () => {
    use({ "/api/tokens/panel/ab": { arms: {}, banner: { level: "grey", text: "no data" } } });
    const view = await abView(context(), signal);
    expect(view.querySelectorAll("usage-table")).toHaveLength(1);
    expect(text(view)).not.toContain("unjoined");
  });

  it("efficiency: five tables with captions", async () => {
    use();
    const view = await efficiencyView(context(), signal);
    expect(view.querySelectorAll("usage-table")).toHaveLength(5);
    clean(view);
  });

  it("efficiency: tolerates missing optional tables and captions", async () => {
    use({ "/api/tokens/panel/efficiency": { captions: {}, commits: [], done: [], estimate: [] } });
    const view = await efficiencyView(context(), signal);
    expect(view.querySelectorAll("usage-table")).toHaveLength(5);
  });
});

describe("per todo item", () => {
  it("shows cost per item, repo and stage", async () => {
    use();
    const view = await itemsView(context(), signal);
    expect(view.querySelectorAll(".chart")).toHaveLength(2);
    expect(view.querySelectorAll("usage-table")).toHaveLength(3);
    expect(text(view)).toContain("$15.62");
    expect(text(view)).toContain("todoImplementer");
    clean(view);
  });
});

describe("more panels", () => {
  it("lists the panels without a dedicated view", async () => {
    use();
    const view = await moreIndexView(context(), signal);
    const hrefs = [...view.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("#/more/hooks?cwd=%2Fhome%2Fkuhy");
    expect(hrefs.some((href) => href?.includes("overview"))).toBe(false);
  });

  it("renders any panel: scalars as tiles, lists as tables", async () => {
    use();
    const view = await genericView(context(), signal, "hooks");
    expect(view.querySelectorAll("usage-table").length).toBeGreaterThanOrEqual(3);
    expect(view.querySelector(".crumbs a")?.getAttribute("href")).toBe("#/more?cwd=%2Fhome%2Fkuhy");
    clean(view);
  });

  it("renders a panel with no scalars and no lists as an empty page", async () => {
    use({ "/api/tokens/panel/empty": { filters: { cwd: "" }, flat: [1, 2], mixed: [{ a: 1 }, null] } });
    const view = await genericView(context(), signal, "empty");
    expect(view.querySelector(".tile")).toBeNull();
    expect(view.querySelector("usage-table")).toBeNull();
  });
});
