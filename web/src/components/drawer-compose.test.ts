/** Send to Claude next to the questions: the note box shows in the questions view, and a note never drops an answer. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import type { TaskDetail } from "@/lib/schemas";

import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { ASK_ID, askDetail, freeDetail } from "@/test/fixture-ask";
import { settle } from "@/test/net";

useDrawerHarness();

beforeEach(() => {
  localStorage.clear();
});

const onlyAskCss = readFileSync(join(import.meta.dirname, "..", "styles", "ask-only.css"), "utf8");
const posts = (): string[] => env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => call.init?.body as string);
const note = (): HTMLTextAreaElement => q<HTMLTextAreaElement>("textarea[name=send]");

async function openDetail(detail: TaskDetail): Promise<void> {
  const { id } = detail.card;
  await open(detail.card, { [`GET /api/task/${id}`]: detail, [`POST /api/task/${id}/send`]: { ok: true, task: detail.card } });
}

describe("[T2273] Send to Claude in the questions view", () => {
  it("[T2273] the only-ask stylesheet never hides the note box", () => {
    expect(onlyAskCss).not.toMatch(/only-ask \[data-slot="send"\]/v);
  });

  it("[T2273] shows the note box and one Send button next to spec questions", async () => {
    await openDetail(askDetail(ASK_ID));
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q("[data-slot=send]").hidden).toBe(false);
    expect(document.querySelectorAll("[data-action=send]")).toHaveLength(1);
  });

  it("[T2273] shows the note box next to a plain Claude question and sends a note as typed", async () => {
    const detail = freeDetail();
    await openDetail(detail);
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q("[data-slot=send]").hidden).toBe(false);
    expect(document.querySelectorAll("[data-action=send]")).toHaveLength(1);
    note().value = "Thanks, now we need an interactive way";
    q("[data-action=send]").click();
    await settle(0);
    expect(posts()).toEqual([JSON.stringify({ text: "Thanks, now we need an interactive way" })]);
  });

  it("[T2273] keeps the answer drafts when a note goes out while the questions are open", async () => {
    const detail = askDetail(ASK_ID);
    await openDetail(detail);
    const answer = q<HTMLTextAreaElement>("textarea[name=Q1]");
    answer.value = "My own answer";
    answer.dispatchEvent(new Event("input"));
    note().value = "One more thing first";
    q("[data-action=send]").click();
    await settle(5000);
    expect(posts()).toEqual([JSON.stringify({ text: "One more thing first" })]);
    expect(note().value).toBe("");
    expect(q<HTMLTextAreaElement>("textarea[name=Q1]").value).toBe("My own answer");
    env.drawer.close(false);
    await openDetail(detail);
    expect(q<HTMLTextAreaElement>("textarea[name=Q1]").value).toBe("My own answer");
  });
});

describe("[T2274] the Questions tab counts open questions only", () => {
  it("[T2274] drops the count once every question is answered and counts the rest", async () => {
    const detail = askDetail(ASK_ID);
    const answered = detail.questions.map((question) => ({ ...question, answer: question.recommendation }));
    const working = card("working");
    await openDetail({ ...detail, card: { ...working, id: detail.card.id }, questions: answered });
    expect(q("[data-tab=questions]").textContent).toBe("Questions");
    env.drawer.close(false);
    const [first, ...rest] = detail.questions;
    await openDetail({ ...detail, questions: [{ ...first!, answer: "Done" }, ...rest] });
    expect(q("[data-tab=questions]").textContent).toBe(`Questions (${String(rest.length)})`);
  });
});
