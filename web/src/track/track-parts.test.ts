/** The header, the round history, the child rows and the issue groups, rendered from the shared sample. */
import { describe, expect, it, vi } from "vitest";

import { makeTrack } from "@/test/fixture-track";
import { renderHead } from "@/track/track-head";
import { renderIssues } from "@/track/track-issues";
import { type Expand, renderKids } from "@/track/track-kids";
import { renderRounds } from "@/track/track-rounds";

const NOW = 1_794_325_000;
const ID = "2d0704cd-0";
const open = (...keys: string[]): Expand => ({ has: (key) => keys.includes(key), toggle: vi.fn() });
const all = (element: Element, selector: string): HTMLElement[] => [...element.querySelectorAll<HTMLElement>(selector)];

describe("header", () => {
  it("draws one bar segment per child, bucket by bucket, and a badge for each non-empty bucket", () => {
    const head = renderHead(makeTrack(), NOW);
    const segments = all(head, ".t-bar > i").map((s) => s.dataset.bucket);
    expect(segments).toHaveLength(11);
    expect(segments.slice(0, 3)).toEqual(["done", "done", "ready"]);
    expect(head.querySelector(".t-bar")?.getAttribute("aria-label")).toBe("2 of 11 done");
    expect(all(head, "[data-bucket].t-stat").map((s) => s.dataset.bucket)).toEqual(["done", "ready", "running", "queued", "failed"]);
    expect(head.querySelector("[data-needs] .t-num")?.textContent).toBe("1");
  });

  it("shows the ETA, the round and its step", () => {
    const head = renderHead(makeTrack(), NOW);
    expect(head.querySelector("[data-eta] .t-num")?.textContent).toBe("1h 30m");
    expect(head.querySelector("[data-round] .t-num")?.textContent).toBe("4");
    const steps = all(head, ".t-steps > i");
    expect(steps.map((s) => s.hasAttribute("data-lit"))).toEqual([true, false, false]);
    expect(steps.map((s) => s.hasAttribute("data-now"))).toEqual([true, false, false]);
  });

  it("lights the steps up to the current one", () => {
    const base = makeTrack();
    const round = { ...base.round!, step: "verdict" as const };
    const steps = all(renderHead(makeTrack({ round }), NOW), ".t-steps > i");
    expect(steps.map((s) => s.hasAttribute("data-lit"))).toEqual([true, true, true]);
  });

  it("shows a dash for the ETA, no stepper and no needs badge when nothing is measured or wrong", () => {
    const base = makeTrack();
    const head = renderHead(
      makeTrack({ counts: { ...base.counts, failed: 0, issues: 0 }, eta: { ...base.eta, seconds: null }, needs: 0, round: null }),
      NOW,
    );
    expect(head.querySelector("[data-eta] .t-num")?.textContent).toBe("–");
    expect(head.querySelector(".t-steps")).toBeNull();
    expect(head.querySelector("[data-needs]")).toBeNull();
    expect(head.querySelector('[data-bucket="failed"]')).toBeNull();
    expect(head.querySelector("[data-round] .t-num")?.textContent).toBe("3");
  });

  it("shows why the run waits, with the minutes left", () => {
    const head = renderHead(makeTrack({ resting: { kind: "gateway", until: NOW + 120 } }), NOW);
    expect(head.querySelector('[data-resting="gateway"] .t-num')?.textContent).toBe("2m");
    expect(renderHead(makeTrack(), NOW).querySelector("[data-resting]")).toBeNull();
  });
});

describe("round history", () => {
  it("has a column per round, oldest first, with the width, the doubling and the duration", () => {
    const rounds = renderRounds(makeTrack().rounds);
    const columns = all(rounds, ".t-round");
    expect(columns.map((c) => c.dataset.n)).toEqual(["1", "2"]);
    expect(columns[0]?.dataset.doubled).toBe("true");
    expect(columns[1]?.dataset.doubled).toBe("false");
    expect(columns[0]?.querySelector(".t-round-head")?.textContent).toContain("10m");
    expect(columns[1]?.querySelector('[aria-label^="The next round"]')).toBeNull();
  });

  it("marks each child by verdict, red when it did not count, with a name for the tooltip", () => {
    const chips = all(renderRounds(makeTrack().rounds), ".t-chip");
    expect(chips.map((c) => [c.dataset.verdict, c.dataset.ok])).toEqual([["clean", "true"], ["fixed", "false"], ["escalate", "false"]]);
    expect(chips[0]?.title).toBe("kuhyx/alpha: clean");
    expect(chips[1]?.title).toBe("kuhyx/beta: fixed (permission block), did not count");
    expect(chips[2]?.title).toContain("not a free worker");
    expect(chips[2]?.querySelector(".t-nofree")).not.toBeNull();
    expect(chips[0]?.querySelector(".t-nofree")).toBeNull();
  });

  it("leaves out the duration of a round without timestamps", () => {
    const [first] = makeTrack().rounds;
    const round = { ...first!, ended: null };
    expect(renderRounds([round]).querySelector('[aria-label^="The round took"]')).toBeNull();
  });
});

describe("child rows", () => {
  it("shows status, repo, stage, elapsed, issues, retries and the verdict of each child", () => {
    const list = renderKids(makeTrack().kids, ID, NOW, open());
    const rows = all(list, ".t-kid");
    expect(rows).toHaveLength(6);
    const beta = rows[1]!;
    expect(beta.dataset.status).toBe("ready_to_ship");
    expect(beta.querySelector(".t-repo")?.textContent).toBe("kuhyx/beta");
    expect(beta.querySelector("[data-stage]")?.getAttribute("data-stage")).toBe("gate");
    expect(beta.querySelector('[aria-label^="Elapsed"]')?.textContent).toBe("40m");
    expect(beta.querySelector('[aria-label^="Free-model issues"] .t-num')?.textContent).toBe("3");
    expect(beta.querySelector('[aria-label^="Worker runs "] .t-num')?.textContent).toBe("3");
    expect(beta.querySelector('[aria-label^="Worker runs killed"] .t-num')?.textContent).toBe("1");
    expect(beta.querySelector('[data-verdict="fixed"]')).not.toBeNull();
    expect(beta.querySelector('[aria-label="Free worker"]')).not.toBeNull();
  });

  it("shows the resting reason of a child and leaves out what is empty", () => {
    const rows = all(renderKids(makeTrack().kids, ID, NOW, open()), ".t-kid");
    expect(rows[4]?.querySelector('[data-resting="network"] .t-num')?.textContent).toBe("5m");
    const backlog = rows[5]!;
    expect(backlog.querySelector("[data-stage]")).toBeNull();
    expect(backlog.querySelector('[aria-label^="Elapsed"]')).toBeNull();
    expect(backlog.querySelector('[aria-label^="Free-model issues"]')).toBeNull();
    expect(backlog.querySelector('[aria-label^="Worker runs"]')).toBeNull();
    expect(backlog.querySelector('[aria-label="Free worker"]')).toBeNull();
    expect(backlog.querySelector("[data-verdict]")).toBeNull();
  });

  it("links the worker log only when there is one, and always the live feed through the umbrella drawer", () => {
    const rows = all(renderKids(makeTrack().kids, ID, NOW, open()), ".t-kid");
    const log = rows[0]?.querySelector<HTMLAnchorElement>('[aria-label="Worker log"]');
    expect(log?.getAttribute("href")).toBe("/api/umbrella/2d0704cd-0/log/2d0704cd-1");
    expect(log?.target).toBe("_blank");
    expect(rows[2]?.querySelector('[aria-label="Worker log"]')).toBeNull();
    expect(rows[2]?.querySelector<HTMLAnchorElement>('a[aria-label^="Live feed"]')?.getAttribute("href")).toBe("#umbrella=2d0704cd-0&task=2d0704cd-0");
  });

  it("expands the last issue and the error on click, and only rows that have one", () => {
    const toggle = vi.fn();
    const rows = all(renderKids(makeTrack().kids, ID, NOW, { has: () => false, toggle }), ".t-kid");
    const main = rows[1]!.querySelector<HTMLButtonElement>(".t-kid-main")!;
    expect(main.getAttribute("aria-expanded")).toBe("false");
    expect(main.title).toBe("permission · free-best: Bash(git status) was denied");
    main.click();
    expect(toggle).toHaveBeenCalledWith("2d0704cd-2");
    const none = rows[0]!.querySelector<HTMLButtonElement>(".t-kid-main")!;
    expect(none.disabled).toBe(true);
    expect(none.hasAttribute("aria-expanded")).toBe(false);
    expect(none.title).toBe("Make alpha text-free");
  });

  it("shows the issue and the error of an open row", () => {
    const rows = all(renderKids(makeTrack().kids, ID, NOW, open("2d0704cd-2", "2d0704cd-3")), ".t-kid");
    expect(rows[1]?.dataset.open).toBe("true");
    expect(rows[1]?.querySelector(".t-issue")?.textContent).toBe("permission · free-best: Bash(git status) was denied");
    expect(rows[1]?.querySelector(".t-error")).toBeNull();
    expect(rows[2]?.querySelector(".t-issue")?.textContent).toBe("start: gateway probe: HTTP 503 from http://127.0.0.1:20128/v1/models");
    expect(rows[2]?.querySelector(".t-error")?.textContent).toContain("claude exited without a result");
  });

  it("shows an error even when the child has no logged issue", () => {
    const [first] = makeTrack().kids;
    const kid = { ...first!, error: "boom", last_issue: null };
    const row = renderKids([kid], ID, NOW, open(kid.id)).querySelector(".t-kid")!;
    expect(row.querySelector(".t-issue")).toBeNull();
    expect(row.querySelector(".t-error")?.textContent).toBe("boom");
  });
});

describe("issue groups", () => {
  it("counts each group by phase and model and names the raw log", () => {
    const section = renderIssues(makeTrack().issues, ID, open());
    expect(section.querySelector(".t-issues-head .t-num")?.textContent).toBe("5");
    expect(section.querySelector<HTMLAnchorElement>('a[aria-label="Raw issue log"]')?.getAttribute("href")).toBe("/api/task/2d0704cd-0/issues");
    const groups = all(section, ".t-group");
    expect(groups.map((g) => g.querySelector(".t-phase")?.textContent)).toEqual(["permission", "start"]);
    expect(groups[0]?.querySelector(".t-model")?.textContent).toBe("free-best");
    expect(groups[1]?.querySelector(".t-model")?.textContent).toBe("–");
    expect(groups[0]?.querySelector('[aria-label^="Fixed"] .t-num')?.textContent).toBe("2");
    expect(groups[1]?.querySelector('[aria-label^="Fixed"]')).toBeNull();
  });

  it("opens a group to its raw lines", () => {
    const toggle = vi.fn();
    const closed = renderIssues(makeTrack().issues, ID, { has: () => false, toggle });
    expect(closed.querySelector("pre")).toBeNull();
    closed.querySelector<HTMLButtonElement>(".t-group-main")!.click();
    expect(toggle).toHaveBeenCalledWith("issue:permission:free-best");
    const opened = renderIssues(makeTrack().issues, ID, open("issue:start:"));
    expect(opened.querySelector("pre")?.textContent).toContain('"phase": "start"');
  });
});
