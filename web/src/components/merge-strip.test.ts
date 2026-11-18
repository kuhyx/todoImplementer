import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineMerges, MERGE_POLL_MS, TiMerges } from "@/components/merge-strip";
import { mergeResponse, suggestions } from "@/lib/schemas-merge";
import { contractValidator } from "@/test/contract-ajv";
import { settle, stubFetch } from "@/test/net";

const ENABLED = { enabled: true, id: "merge", label: "Merge", reason: null } as const;
const DISMISS = { enabled: true, id: "dismiss", label: "Dismiss", reason: null } as const;
const suggestion = (merge: object = ENABLED): object => {
  return {
    actions: [merge, DISMISS],
    id: GROUP,
    members: [
      { id: "aaaaaaaa-0", repo: "kuhyx/a", title: "Make a text-free" },
      { id: "bbbbbbbb-1", repo: "kuhyx/b", title: "Make b text-free" },
      { id: "cccccccc-0", repo: "kuhyx/c", title: "Make c text-free" },
    ],
    reason: "same change",
    title: "Text-free sweep",
  };
};
const GROUP = "0123456789ab";
const q = <T extends Element = HTMLElement>(sel: string): T => {
  const element = document.querySelector<T>(sel);
  if (element === null) throw new Error(`no ${sel}`);
  return element;
};

async function mount(routes: Record<string, unknown>): Promise<TiMerges> {
  stubFetch(routes);
  const element = new TiMerges();
  document.body.append(element);
  await settle(0);
  return element;
}

beforeEach(() => {
  vi.useFakeTimers();
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok">';
  document.body.replaceChildren();
  defineMerges();
  defineMerges();
});
afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("merge suggestions strip", () => {
  it("stays hidden while there is nothing to suggest", async () => {
    const element = await mount({ "GET /api/merges": { suggestions: [] } });
    expect(element.hidden).toBe(true);
    expect(element.children).toHaveLength(0);
  });

  it("shows a card with an icon header, the member count and every member title", async () => {
    const element = await mount({ "GET /api/merges": { suggestions: [suggestion()] } });
    expect(element.hidden).toBe(false);
    expect(q(".merge-count").textContent).toBe("3");
    expect(document.body.textContent).not.toContain("Text-free sweep"); // the proposed title is API-only
    expect(q(".merge-glyph svg")).toBeTruthy();
    expect([...document.querySelectorAll(".merge-member-title")].map((m) => m.textContent)).toEqual([
      "Make a text-free",
      "Make b text-free",
      "Make c text-free",
    ]);
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".merge-actions button")];
    expect(buttons.map((b) => [b.dataset.action, b.getAttribute("aria-label"), b.textContent])).toEqual([
      ["merge", "Merge", ""],
      ["dismiss", "Dismiss", ""],
    ]);
  });

  it("a disabled merge keeps the server's reason as its tooltip and does not post", async () => {
    const off = { enabled: false, id: "merge", label: "Merge", reason: "aaaaaaaa-0 has a live run (plan)" };
    const stub = stubFetch({ "GET /api/merges": { suggestions: [suggestion(off)] } });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    const merge = q<HTMLButtonElement>("[data-action=merge]");
    expect(merge.disabled).toBe(true);
    expect(merge.title).toBe("aaaaaaaa-0 has a live run (plan)");
    merge.click();
    await settle(0);
    expect(stub.calls.filter((c) => c.init?.method === "POST")).toHaveLength(0);
    expect(q<HTMLButtonElement>("[data-action=dismiss]").disabled).toBe(false);
  });

  it("merge posts an empty body with the CSRF header, then shows the fresh list", async () => {
    const stub = stubFetch({
      [`POST /api/merge/${GROUP}/merge`]: { new_id: "aaaaaaaa-3", ok: true, suggestions: [] },
      "GET /api/merges": { suggestions: [suggestion()] },
    });
    const element = new TiMerges();
    document.body.append(element);
    await settle(0);
    q("[data-action=merge]").click();
    const post = stub.calls.find((c) => c.init?.method === "POST");
    expect(post?.init?.body).toBe("{}");
    expect(post?.init?.headers).toMatchObject({ "X-Todoimpl-Token": "tok" });
    expect(q("article").hasAttribute("data-busy")).toBe(true);
    await settle(0);
    expect(element.hidden).toBe(true);
  });

  it("dismiss posts to the dismiss route", async () => {
    const stub = stubFetch({
      [`POST /api/merge/${GROUP}/dismiss`]: { new_id: null, ok: true, suggestions: [] },
      "GET /api/merges": { suggestions: [suggestion()] },
    });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    q("[data-action=dismiss]").click();
    await settle(0);
    expect(stub.calls.some((c) => c.url === `/api/merge/${GROUP}/dismiss`)).toBe(true);
  });

  it("a wait of 1 s shows a spinner named for what it waits on; busy shows at once", async () => {
    stubFetch({
      [`POST /api/merge/${GROUP}/merge`]: async () => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { new_id: "aaaaaaaa-3", ok: true, suggestions: [] };
      },
      "GET /api/merges": { suggestions: [suggestion()] },
    });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    q("[data-action=merge]").click();
    expect(q<HTMLButtonElement>("[data-action=dismiss]").disabled).toBe(true);
    expect(document.querySelector(".spinner")).toBeNull();
    await settle(1000);
    expect(q(".spinner").getAttribute("aria-label")).toBe("Merging");
    await settle(600);
    expect(document.querySelector(".spinner")).toBeNull();
  });

  it("a refused click shakes the card and shows the server's message", async () => {
    stubFetch({
      [`POST /api/merge/${GROUP}/merge`]: () =>
        Response.json({ error: { code: "disabled", message: "a member has a live run" }, ok: false }, { status: 409 }),
      "GET /api/merges": { suggestions: [suggestion()] },
    });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    q("[data-action=merge]").click();
    await settle(0);
    expect(q("article").hasAttribute("data-error")).toBe(true);
    expect(q(".toast-error").textContent).toBe("a member has a live run");
    expect(q<HTMLButtonElement>("[data-action=merge]").disabled).toBe(false);
  });

  it("a click without a CSRF token shakes the card and sends nothing", async () => {
    document.head.replaceChildren();
    const stub = stubFetch({ "GET /api/merges": { suggestions: [suggestion()] } });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    q("[data-action=merge]").click();
    expect(q("article").hasAttribute("data-error")).toBe(true);
    expect(stub.calls.filter((c) => c.init?.method === "POST")).toHaveLength(0);
  });

  it("polls, keeps the last list when a poll fails and stops when removed", async () => {
    let isFail = false;
    const stub = stubFetch({
      "GET /api/merges": () => (isFail ? Response.json({ no: 1 }, { status: 500 }) : { suggestions: [suggestion()] }),
    });
    const element = new TiMerges();
    document.body.append(element);
    await settle(0);
    isFail = true;
    await settle(MERGE_POLL_MS);
    expect(stub.calls).toHaveLength(2);
    expect(element.hidden).toBe(false);
    expect(document.querySelectorAll("article")).toHaveLength(1);
    element.remove();
    await settle(MERGE_POLL_MS * 2);
    expect(stub.calls).toHaveLength(2);
    element.disconnectedCallback();
  });

  it("an unchanged poll does not repaint the cards", async () => {
    stubFetch({ "GET /api/merges": { suggestions: [suggestion()] } });
    document.body.append(document.createElement("ti-merges"));
    await settle(0);
    const card = q("article");
    await settle(MERGE_POLL_MS);
    expect(q("article")).toBe(card);
  });
});

describe("contract mirror", () => {
  const good = { suggestions: [suggestion()] };
  it("agrees with merge.schema.json on the list, good and bad", () => {
    const validate = contractValidator("merge");
    const bad = [{ suggestions: [{ ...suggestion(), id: "SHORT" }] }, { suggestions: [{ ...suggestion(), extra: 1 }] }, {}];
    for (const value of [good, ...bad]) expect(suggestions.safeParse(value).success).toBe(validate(value));
    const off = { enabled: false, id: "merge", label: "Merge", reason: null };
    const noReason = { suggestions: [suggestion(off)] };
    expect(suggestions.safeParse(noReason).success).toBe(validate(noReason));
    expect(validate(noReason)).toBe(false);
  });

  it("agrees on the POST answers", () => {
    const validate = contractValidator("merge", "response");
    const values = [
      { new_id: null, ok: true, suggestions: [] },
      { new_id: "aaaaaaaa-3", ok: true, suggestions: [suggestion()] },
      { error: { code: "upstream_unavailable", message: "x" }, ok: false },
      { error: { code: "weird", message: "x" }, ok: false },
      { ok: true, suggestions: [] },
    ];
    for (const value of values) expect(mergeResponse.safeParse(value).success).toBe(validate(value));
  });
});
