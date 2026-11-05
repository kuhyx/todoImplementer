/** The /api/tokens fixtures, the Zod mirrors and contracts/tokens-*.schema.json must agree. */
import type { z } from "zod";

import { describe, expect, it } from "vitest";

import { contractValidator, panelContracts } from "@/test/contract-ajv";
import { fixtures } from "@/usage/fixtures/load";
import { contextFileDetail, contextPanel, overviewPanel, sessionDetail, sessionsPanel, tokensIndex } from "@/usage/schemas";
import { abPanel, anomaliesPanel, efficiencyPanel, genericPanel, itemsPanel, leversPanel } from "@/usage/schemas-panels";

type Zod = z.ZodType;
interface Route {
  readonly contract: readonly [string, string];
  readonly fixture: unknown;
  readonly zod: Zod;
}

const files = panelContracts();
const panel = (name: string): readonly [string, string] => [files.get(name) ?? "missing", name];
const ROUTES = {
  ab: { contract: panel("ab"), fixture: fixtures.ab, zod: abPanel },
  anomalies: { contract: panel("anomalies"), fixture: fixtures.anomalies, zod: anomaliesPanel },
  context: { contract: panel("context"), fixture: fixtures.context, zod: contextPanel },
  contextFile: { contract: ["tokens-detail", "context_file"], fixture: fixtures.contextFile, zod: contextFileDetail },
  efficiency: { contract: panel("efficiency"), fixture: fixtures.efficiency, zod: efficiencyPanel },
  hooks: { contract: panel("hooks"), fixture: fixtures.hooks, zod: genericPanel },
  index: { contract: ["tokens-index", "index"], fixture: fixtures.index, zod: tokensIndex },
  items: { contract: ["tokens-detail", "items"], fixture: fixtures.items, zod: itemsPanel },
  levers: { contract: panel("levers"), fixture: fixtures.levers, zod: leversPanel },
  overview: { contract: panel("overview"), fixture: fixtures.overview, zod: overviewPanel },
  session: { contract: ["tokens-detail", "session"], fixture: fixtures.session, zod: sessionDetail },
  sessions: { contract: panel("sessions"), fixture: fixtures.sessions, zod: sessionsPanel },
} satisfies Record<string, Route>;

const validator = (route: Route): ReturnType<typeof contractValidator> => contractValidator(...route.contract);
const byName = (a: string, b: string): number => a.localeCompare(b);

describe("tokens contracts", () => {
  it.each(Object.entries(ROUTES))("%s: the fixture is valid in the contract and in the Zod mirror", (_name, route) => {
    const check = validator(route);
    expect(check(route.fixture), JSON.stringify(check.errors?.slice(0, 3))).toBe(true);
    expect(route.zod.safeParse(route.fixture).success).toBe(true);
  });

  it("covers every fixture the usage page loads", () => {
    expect(Object.keys(ROUTES).toSorted(byName)).toEqual(Object.keys(fixtures).toSorted(byName));
  });

  it("defines a contract for every panel the index fixture lists", () => {
    const missing = fixtures.index.panels.map((p) => p.name).filter((name) => !files.has(name));
    expect(missing).toEqual([]);
  });

  it("requires at least the keys the Zod mirror requires", () => {
    const unrequired: string[] = [];
    for (const [name, route] of Object.entries(ROUTES)) {
      if (name === "ab" || name === "hooks") continue;
      const required = (validator(route).schema as { required?: string[] }).required ?? [];
      const shape = (route.zod as z.ZodObject<Record<string, z.ZodType>>).shape;
      for (const [key, field] of Object.entries(shape)) {
        if (!field.safeParse(undefined).success && !required.includes(key)) unrequired.push(`${name}.${key}`);
      }
    }
    expect(unrequired).toEqual([]);
  });

  it("rejects a missing key and a wrong type in both, and an unknown key in the contract only", () => {
    const sessions = fixtures.sessions as Record<string, unknown>;
    const without = Object.fromEntries(Object.entries(sessions).filter(([key]) => key !== "sessions"));
    const broken = [without, { ...sessions, surprise: 1 }, { ...sessions, sessions: "none" }];
    const check = validator(ROUTES.sessions);
    expect(broken.map((value) => check(value))).toEqual([false, false, false]);
    expect(broken.map((value) => sessionsPanel.safeParse(value).success)).toEqual([false, true, false]);
  });

  it("rejects an unlisted A/B banner level and a body that is not the error shape", () => {
    const ab = fixtures.ab as { banner: { level: string; text: string } };
    expect(validator(ROUTES.ab)({ ...ab, banner: { ...ab.banner, level: "purple" } })).toBe(false);
    const error = contractValidator("tokens-common", "error");
    expect(error({ error: "no such panel: x" })).toBe(true);
    expect(error({ message: "x" })).toBe(false);
  });
});
