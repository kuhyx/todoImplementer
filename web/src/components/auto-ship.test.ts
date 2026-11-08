import { describe, expect, it } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { restoreInputs, snapshotInputs } from "@/lib/boot";
import { bodyFor } from "@/lib/routes";
import { action } from "@/lib/schemas-common";
import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { settle } from "@/test/net";

useDrawerHarness();

const LABEL = "Auto-ship when checks pass";
function start(isEnabled = true): Action {
  const reason = isEnabled ? null : "the note has no done_check";
  return { enabled: true, id: "start", label: "Start", option: { enabled: isEnabled, id: "auto_ship", label: LABEL, reason }, reason: null };
}

async function startWith(option: Action, shouldTick: boolean): Promise<unknown> {
  const c = { ...card("backlog"), actions: [option] };
  await open(c, { [`POST /api/task/${c.id}/start`]: () => ({ ok: true, task: c }) });
  if (shouldTick) q<HTMLInputElement>("input[name=auto_ship]").click();
  q("[data-action=start]").click();
  await settle(0);
  const post = env.stub.calls.find((call) => call.init?.method === "POST");
  return JSON.parse(typeof post?.init?.body === "string" ? post.init.body : "null") as unknown;
}

describe("auto-ship option", () => {
  it("the schema takes an option and refuses a disabled one without a reason", () => {
    expect(action.safeParse(start()).success).toBe(true);
    const bad = { ...start(), option: { enabled: false, id: "auto_ship", label: LABEL, reason: null } };
    expect(action.safeParse(bad).success).toBe(false);
  });

  it("renders an unticked checkbox beside Start and sends auto_ship false by default", async () => {
    expect(await startWith(start(), false)).toEqual({ auto_ship: false });
    const box = q<HTMLInputElement>("input[name=auto_ship]");
    expect(box.checked).toBe(false);
    expect(box.closest("label")?.textContent).toBe(LABEL);
  });

  it("sends auto_ship true when ticked", async () => {
    expect(await startWith(start(), true)).toEqual({ auto_ship: true });
  });

  it("a disabled option shows its reason and never sends true", async () => {
    expect(await startWith(start(false), true)).toEqual({ auto_ship: false });
    expect(q<HTMLInputElement>("input[name=auto_ship]").disabled).toBe(true);
    expect(q("[data-slot=actions]").textContent).toContain("the note has no done_check");
  });

  it("Retry without an option sends an empty body", () => {
    expect(bodyFor("start", {})).toEqual({});
    expect(bodyFor("start", { autoShip: true })).toEqual({ auto_ship: true });
  });

  it("a repaint keeps the tick", () => {
    document.body.innerHTML = '<div id="r"><input type="checkbox" name="auto_ship" data-keep></div>';
    const root = q("#r");
    q<HTMLInputElement>("input").checked = true;
    const snap = snapshotInputs(root);
    root.innerHTML = '<input type="checkbox" name="auto_ship" data-keep>';
    restoreInputs(root, snap);
    expect(q<HTMLInputElement>("input").checked).toBe(true);
  });
});
