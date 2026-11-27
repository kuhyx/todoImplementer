/** The no-limit runner's row: icons and the repo name only, words in title and aria-label; contract and mirror agree. */
import { describe, expect, it } from "vitest";

import type { NoLimit } from "@/lib/schemas-nolimit";

import { renderNoLimit } from "@/components/nolimit-strip";
import { renderUsage } from "@/components/usage-strip";
import { usage } from "@/lib/schemas";
import { contractValidator } from "@/test/contract-ajv";
import { makeUsage } from "@/test/fixture-detail";
import { NOW } from "@/test/fixtures";

const row = (over: Partial<NoLimit> = {}): NoLimit => ({ active: true, at: NOW - 120, repo: "kcd2-dice-solver", result: "red", ...over });

function agree(value: unknown): boolean[] {
  return [contractValidator("usage")(value), usage.safeParse(value).success];
}

describe("no-limit row", () => {
  it("[T2549] shows the wrench, the repo and the result icon, words only in the title", () => {
    const element = renderNoLimit(row(), NOW);
    expect(element?.dataset.active).toBe("true");
    expect(element?.textContent).toBe("kcd2-dice-solver");
    expect(element?.querySelector("[data-result]")?.getAttribute("data-tone")).toBe("danger");
    expect(element?.querySelectorAll("svg")).toHaveLength(2);
    expect(element?.title).toBe("No-limit runner: on, no Claude route; last: kcd2-dice-solver, a step failed, tickets filed, 2 min ago");
  });

  it("rests dimmed with the last result, hides before its first visit and without a row", () => {
    const resting = renderNoLimit(row({ active: false, result: "slow" }), NOW);
    expect(resting?.dataset.active).toBe("false");
    expect(resting?.title.startsWith("No-limit runner: resting; last: kcd2-dice-solver, a step ran past 60 s")).toBe(true);
    expect(renderNoLimit(row({ active: false, at: null, repo: null, result: null }), NOW)).toBeNull();
    expect(renderNoLimit(undefined, NOW)).toBeNull();
    const fresh = renderNoLimit(row({ at: null, repo: null, result: null }), NOW);
    expect(fresh?.title).toBe("No-limit runner: on, no Claude route");
    expect(fresh?.querySelectorAll("svg")).toHaveLength(1);
  });

  it("names every result with its own icon", () => {
    const results = ["deployed", "pushed", "green", "red", "slow", "stopped", "readonly"] as const;
    const paths = results.map((result) => renderNoLimit(row({ result }), NOW)?.querySelector("[data-result] svg path")?.getAttribute("d"));
    const distinct = new Set(paths);
    expect(distinct.size).toBe(results.length);
  });

  it("sits in the usage strip", () => {
    const element = renderUsage({ ...makeUsage(), nolimit: row({ result: "deployed" }) }, null, null, null, NOW);
    expect(element.querySelector(".nolimit-strip [data-result='deployed']")).not.toBeNull();
    expect(renderUsage(makeUsage(), null, null, null, NOW).querySelector(".nolimit-strip")).toBeNull();
  });

  it("agrees with the contract, good and bad", () => {
    expect(agree({ ...makeUsage(), nolimit: row() })).toEqual([true, true]);
    expect(agree({ ...makeUsage(), nolimit: row({ at: null, repo: null, result: null }) })).toEqual([true, true]);
    expect(agree({ ...makeUsage(), nolimit: { ...row(), result: "weird" } })).toEqual([false, false]);
    expect(agree({ ...makeUsage(), nolimit: { ...row(), extra: 1 } })).toEqual([false, false]);
  });
});
