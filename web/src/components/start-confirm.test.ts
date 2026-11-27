import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { isStartConfirmed } from "@/components/start-confirm";
import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { settle } from "@/test/net";

useDrawerHarness();

const WAITS = { id: "aaaaaaaa-0", priority: "high", title: "urgent repo" };

beforeAll(() => {
  // jsdom has no modal dialogs: open and close toggle the attribute like a browser would
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement): void {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement): void {
    this.removeAttribute("open");
  };
});

afterEach(() => {
  for (const dialog of document.querySelectorAll("dialog")) dialog.remove();
});

const dialog = (): HTMLDialogElement => {
  const found = document.querySelector<HTMLDialogElement>("dialog[data-start-confirm]");
  if (found === null) throw new Error("no start-confirm dialog");
  return found;
};
const button = (which: string): HTMLButtonElement => {
  const found = dialog().querySelector<HTMLButtonElement>(`[data-start-confirm=${CSS.escape(which)}]`);
  if (found === null) throw new Error(`no ${which} button`);
  return found;
};

describe("start confirm modal", () => {
  it("[T2583] names the waiting card and resolves on each way out", async () => {
    const outside = vi.fn();
    document.body.addEventListener("keydown", outside);
    for (const [act, expected] of [["go", true], ["back", false], ["cancel", false], ["scrim", false]] as const) {
      const answer = isStartConfirmed(WAITS);
      expect(dialog().hasAttribute("open")).toBe(true);
      expect(dialog().querySelector("[data-waits]")?.textContent).toBe("urgent repo");
      expect(document.activeElement).toBe(button("go"));
      dialog().dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }));
      dialog().querySelector("h2")?.click(); // a click inside is not the scrim
      if (act === "cancel") dialog().dispatchEvent(new Event("cancel", { cancelable: true }));
      else if (act === "scrim") dialog().click();
      else button(act).click();
      expect(await answer).toBe(expected);
      expect(document.querySelector("dialog")).toBeNull();
    }
    expect(outside).not.toHaveBeenCalled(); // the drawer never sees the modal's keys
  });

  it("[T2583] Start on a card a higher one outranks asks first; Back sends nothing, Start anyway starts", async () => {
    const start = { enabled: true, id: "start" as const, label: "Start", reason: null, waits: WAITS };
    const c = { ...card("backlog"), actions: [start] };
    await open(c, { [`POST /api/task/${c.id}/start`]: () => ({ ok: true, task: c }) });
    const posts = (): number => env.stub.calls.filter((call) => call.init?.method === "POST").length;
    q("[data-action=start]").click();
    await settle(0);
    button("back").click();
    await settle(0);
    expect(posts()).toBe(0);
    q("[data-action=start]").click();
    await settle(0);
    button("go").click();
    await settle(300);
    expect(env.stub.calls.find((call) => call.init?.method === "POST")?.url).toBe(`/api/task/${c.id}/start`);
  });
});
