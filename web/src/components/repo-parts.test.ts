/** Repo task parts and the per-repo lock badge: icons and numbers only, contract-checked fixtures. */
import { describe, expect, it } from "vitest";

import type { RepoPart } from "@/lib/schemas-common";
import type { UmbrellaDetail } from "@/lib/schemas-umbrella";

import { renderCard } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { partsStrip, renderParts, waitsBadge } from "@/components/repo-parts";
import { renderUmbrella } from "@/components/umbrella";
import { taskDetail } from "@/lib/schemas";
import { taskCard } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards, NOW } from "@/test/fixtures";

const PARTS: RepoPart[] = [
  { edit: { enabled: false, reason: "ticked" }, id: "aaaa1111-0", state: "done", steps: null, title: "Text-free leftovers" },
  { edit: { enabled: false, reason: "on it" }, id: "aaaa1111-1", state: "working", steps: { done: 1, total: 3 }, title: "Server strings" },
  { edit: { enabled: true, reason: null }, id: "aaaa1111-2", state: "todo", steps: null, title: "Make tutor text-free" },
  { edit: { enabled: true, reason: null }, id: "bbbb2222-0", state: "human", steps: null, title: "MANUAL WORK REQUIRED: sign in" },
  { edit: { enabled: false, reason: "older run" }, id: "cccc3333-4", state: "held", steps: null, title: "Older run" },
];
const ROW: UmbrellaDetail["rows"][number] = {
  cost_usd: 0,
  error: null,
  free: null,
  id: "dddd4444-1",
  issues: 0,
  repo: "kuhyx/alpha",
  round: null,
  stage: null,
  status: "queued",
  title: "Alpha",
  verdict: null,
  waits_on: "eeee5555-0",
};

function baseCard() {
  const [card] = makeCards();
  if (card === undefined) throw new Error("no fixture card");
  return card;
}

describe("repo task parts", () => {
  it("[T1916] a repo task card shows its parts as icons and a queued card shows what it waits on", () => {
    const card = { ...baseCard(), parts: PARTS, status: "queued" as const, waits_on: "eeee5555-0" };
    expect(taskCard.safeParse(card).success).toBe(true);
    expect(contractValidator("common", "task_card")(card)).toBe(true);
    const node = renderCard(card, NOW);
    const marks = [...node.querySelectorAll("[data-parts] [data-state]")];
    expect(marks.map((mark) => mark.getAttribute("data-state"))).toEqual(["done", "working", "todo", "human", "held"]);
    expect(node.querySelector("[data-parts]")?.textContent).toBe("");
    expect(node.querySelector('[data-waits-on="eeee5555-0"]')?.getAttribute("aria-label")).toBe("Waits on eeee5555-0");
  });

  it("names every part and its state in aria-label and title, one icon each", () => {
    const strip = partsStrip(PARTS);
    expect(strip.querySelectorAll("svg")).toHaveLength(5);
    const labels = [...strip.querySelectorAll("[aria-label]")].map((mark) => mark.getAttribute("aria-label"));
    expect(labels).toEqual([
      "Text-free leftovers: Done",
      "Server strings: Working",
      "Make tutor text-free: To do",
      "MANUAL WORK REQUIRED: sign in: Yours",
      "Older run: Own run",
    ]);
    expect(strip.querySelector("[title='Older run: Own run']")).not.toBeNull();
  });

  it("lists the parts in the drawer with titles as user content and steps as icon plus number", () => {
    const list = renderParts(PARTS);
    const rows = list.querySelectorAll(".p-row");
    expect(rows).toHaveLength(5);
    expect(rows[1]?.querySelector(".p-title")?.textContent).toBe("Server strings");
    expect(rows[1]?.querySelector(".p-steps")?.textContent).toBe("1/3");
    expect(rows[1]?.querySelector('[aria-label="Steps 1/3"]')).not.toBeNull();
    expect(rows[0]?.querySelector(".p-steps")).toBeNull();
    expect(rows[3]?.getAttribute("data-state")).toBe("human");
  });

  it("the head carries the checklist and the lock only when the card has them", () => {
    const card = { ...baseCard(), parts: PARTS, waits_on: "eeee5555-0" };
    const head = renderHead(makeDetail(card));
    expect(head.querySelector("[data-parts-detail]")).not.toBeNull();
    expect(head.querySelector("[data-waits-on]")).not.toBeNull();
    const plain = renderHead(makeDetail(baseCard()));
    expect(plain.querySelector("[data-parts-detail]")).toBeNull();
    expect(plain.querySelector("[data-waits-on]")).toBeNull();
    const empty = renderHead(makeDetail({ ...baseCard(), parts: [], waits_on: null }));
    expect(empty.querySelector("[data-parts-detail]")).toBeNull();
    expect(renderCard({ ...baseCard(), parts: [] }, NOW).querySelector("[data-parts]")).toBeNull();
    expect(renderCard({ ...baseCard(), waits_on: null }, NOW).querySelector("[data-waits-on]")).toBeNull();
  });

  it("the umbrella child row shows the lock when the child waits on a run of its repo", () => {
    const detail: UmbrellaDetail = { round: 1, rounds: [], rows: [ROW, { ...ROW, id: "ffff6666-1", waits_on: null }, { ...ROW, id: "gggg7777-1", waits_on: undefined }], width: 1 };
    const rows = renderUmbrella(detail, "dddd4444-0").querySelectorAll(".u-row");
    expect(rows[0]?.querySelector('[data-waits-on="eeee5555-0"]')).not.toBeNull();
    expect(rows[1]?.querySelector("[data-waits-on]")).toBeNull();
    expect(rows[2]?.querySelector("[data-waits-on]")).toBeNull();
  });

  it("agrees with the JSON schema on parts, steps and the lock", () => {
    const detail = { ...makeDetail({ ...baseCard(), parts: PARTS, waits_on: "eeee5555-0" }) };
    expect(taskDetail.safeParse(detail).success).toBe(true);
    expect(contractValidator("task")(detail)).toBe(true);
    const bad = { ...baseCard(), parts: [{ ...PARTS[0], state: "nope" }] };
    expect(taskCard.safeParse(bad).success).toBe(false);
    expect(contractValidator("common", "task_card")(bad)).toBe(false);
    const noSteps = { ...baseCard(), parts: [{ ...PARTS[1], steps: { done: 0, total: 0 } }] };
    expect(taskCard.safeParse(noSteps).success).toBe(false);
    expect(contractValidator("common", "task_card")(noSteps)).toBe(false);
    const row = { ...ROW, waits_on: "bad" };
    expect(contractValidator("umbrella", "row")(ROW)).toBe(true);
    expect(contractValidator("umbrella", "row")(row)).toBe(false);
  });

  it("waitsBadge is one lock icon with no text", () => {
    const badge = waitsBadge("eeee5555-0");
    expect(badge.textContent).toBe("");
    expect(badge.querySelectorAll("svg")).toHaveLength(1);
  });
});
