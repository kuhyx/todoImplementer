/** Umbrella card progress and drawer rows: icons and numbers, contract-checked fixtures. */
import { describe, expect, it } from "vitest";

import type { UmbrellaDetail, UmbrellaRow } from "@/lib/schemas-umbrella";

import { renderCard } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { renderUmbrella, umbrellaProgress } from "@/components/umbrella";
import { taskDetail } from "@/lib/schemas";
import { taskCard } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards, NOW } from "@/test/fixtures";

const COUNTS = { done: 1, failed: 0, issues: 3, queued: 2, ready: 1, round: 2, running: 1, total: 5, width: 4 };
const ROW: UmbrellaRow = {
  cost_usd: 0.5,
  error: null,
  free: true,
  id: "aaaa1111-0",
  issues: 2,
  repo: "kuhyx/alpha",
  round: 1,
  stage: "live_check",
  status: "working",
  title: "Alpha",
  verdict: "fixed",
};
const DETAIL: UmbrellaDetail = {
  round: 2,
  rounds: [
    { children: [{ checks: true, detail: "", free: true, id: "aaaa1111-0", ok: true, verdict: "clean" }], n: 1, next: 2, width: 1 },
    { children: [{ checks: false, detail: "x", free: true, id: "bbbb2222-0", ok: false, verdict: "fixed" }], n: 2, next: 2, width: 2 },
  ],
  rows: [
    ROW,
    { ...ROW, error: "Pre-push gate is red", free: false, id: "bbbb2222-0", issues: 0, round: null, status: "needs_you", verdict: "escalate" },
    { ...ROW, id: "cccc3333-0", issues: 0, status: "done", verdict: "clean" },
    { ...ROW, free: null, id: "dddd4444-0", issues: 0, round: null, status: "backlog", verdict: null },
  ],
  width: 4,
};

function umbrellaCard() {
  const [card] = makeCards();
  if (card === undefined) throw new Error("no fixture card");
  return { ...card, umbrella: COUNTS };
}

describe("umbrella contract", () => {
  it("agrees with the JSON schema on the card and the detail", () => {
    const card = umbrellaCard();
    expect(taskCard.safeParse(card).success).toBe(true);
    expect(contractValidator("common", "task_card")(card)).toBe(true);
    const detail = { ...makeDetail(card), umbrella: DETAIL };
    expect(taskDetail.safeParse(detail).success).toBe(true);
    expect(contractValidator("task")(detail)).toBe(true);
  });

  it("rejects the same bad counts in both", () => {
    const bad = { ...umbrellaCard(), umbrella: { ...COUNTS, width: 0 } };
    expect(taskCard.safeParse(bad).success).toBe(false);
    expect(contractValidator("common", "task_card")(bad)).toBe(false);
  });
});

describe("umbrella progress on the card", () => {
  it("shows one icon and number per non-empty bucket, the width and the issue count, without words", () => {
    const line = umbrellaProgress(COUNTS);
    const buckets = [...line.querySelectorAll("[data-bucket]")].map((node) => node.getAttribute("data-bucket"));
    expect(buckets).toEqual(["done", "running", "ready", "queued"]);
    expect(line.querySelector('[data-bucket="failed"]')).toBeNull();
    expect(line.textContent).toBe("111243");
    expect(line.querySelectorAll("svg")).toHaveLength(6);
    expect(line.querySelector('[aria-label="Round width 4"]')).not.toBeNull();
    expect(line.querySelector('[aria-label="Free-model issues 3"]')).not.toBeNull();
  });

  it("drops the issue badge at zero and the card renders the line only for umbrellas", () => {
    expect(umbrellaProgress({ ...COUNTS, issues: 0 }).querySelector('[aria-label^="Free-model"]')).toBeNull();
    expect(renderCard(umbrellaCard(), NOW).querySelector("[data-umbrella]")).not.toBeNull();
    const [plain] = makeCards();
    expect(plain && renderCard(plain, NOW).querySelector("[data-umbrella]")).toBeNull();
  });
});

describe("umbrella rows in the drawer", () => {
  const block = renderUmbrella(DETAIL, "aaaa1111-0");

  it("lists a row per child with status, repo, round, verdict, free and issue badges", () => {
    const rows = block.querySelectorAll(".u-row");
    expect(rows).toHaveLength(4);
    expect(rows[0]?.querySelector(".u-repo")?.textContent).toBe("kuhyx/alpha");
    expect(rows[0]?.querySelector('[data-verdict="fixed"]')).not.toBeNull();
    expect(rows[0]?.querySelector('[aria-label="Free worker"]')).not.toBeNull();
    expect(rows[0]?.querySelector('[aria-label="Free-model issues 2"]')).not.toBeNull();
    expect(rows[1]?.querySelector(".u-error")?.textContent).toBe("Pre-push gate is red");
    expect(rows[1]?.querySelector('[data-verdict="escalate"]')).not.toBeNull();
    expect(rows[3]?.querySelector("[data-verdict]")).toBeNull();
    expect(rows[3]?.querySelector('[aria-label="Free worker"]')).toBeNull();
  });

  it("marks the rounds that doubled the width and links the raw issue log", () => {
    const rounds = [...block.querySelectorAll(".u-round")];
    expect(rounds.map((r) => [r.textContent, r.getAttribute("data-doubled")])).toEqual([["1", "true"], ["2", "false"]]);
    const link = block.querySelector("a.u-issues");
    expect(link?.getAttribute("href")).toBe("/api/task/aaaa1111-0/issues");
    expect(link?.textContent).toBe("2");
  });

  it("[T1887] shows a coached verdict with its own icon", () => {
    const coached = renderUmbrella({ ...DETAIL, rows: [{ ...ROW, verdict: "coached" }] }, "aaaa1111-0");
    expect(coached.querySelector('[data-verdict="coached"]')).not.toBeNull();
  });

  it("omits the issue link when nothing went wrong and the head carries the block", () => {
    const clean = renderUmbrella({ ...DETAIL, rows: [{ ...ROW, issues: 0 }] }, "aaaa1111-0");
    expect(clean.querySelector("a.u-issues")).toBeNull();
    const head = renderHead({ ...makeDetail(umbrellaCard()), umbrella: DETAIL });
    expect(head.querySelector("[data-umbrella-detail]")).not.toBeNull();
    expect(renderHead(makeDetail(umbrellaCard())).querySelector("[data-umbrella-detail]")).toBeNull();
  });
});
