/** Move to the board: offered only where the server says `movable`, its reason in the title otherwise; one row or a bulk of up to five. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { make, sessionRows, sid } from "#fixtures/fixture-sessions";
import { click, install, mount, q, uninstall } from "#fixtures/sessions-harness";

beforeEach(install);
afterEach(uninstall);

const row = (id: number): string => `tr[data-id="${sid(id)}"]`;
const board = (scope: string): string => `${scope} button[data-action="handoff"]`;
const pick = async (app: Element, ...numbers: number[]): Promise<void> => {
  for (const number_ of numbers) await click(q(app, `${row(number_)} input[type="checkbox"]`));
};

describe("one session", () => {
  it("moves a movable session and reloads the list", async () => {
    const harness = await mount();
    const button = q<HTMLButtonElement>(harness.app, board(row(4)));
    expect(button.disabled).toBe(false);
    expect(button.textContent).toBe("");
    expect(button.getAttribute("aria-label")).toBe("move to the board");
    await click(button);
    expect(harness.posts()).toEqual([{ body: { id: sid(4) }, headers: { "Content-Type": "application/json", "X-Todoimpl-Token": "tok" }, url: "/api/sessions/handoff" }]);
    expect(harness.stub.calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    expect(q(harness.app, `${row(4)} .outcome`).dataset.kind).toBe("ok");
  });

  it("disables an unmovable row with the server's reason as its title", async () => {
    const { app } = await mount();
    const button = q<HTMLButtonElement>(app, board(row(1)));
    expect(button.disabled).toBe(true);
    expect(button.title).toBe(make(1).move_reason);
  });

  it("shows a refusal as a lock with the server's words", async () => {
    const harness = await mount("", { reply: { argv: [], ok: false, refused: true, stderr: "", stdout: "", summary: "Nothing moved: already open." } });
    await click(q(harness.app, board(row(5))));
    expect(q(harness.app, `${row(5)} .outcome`).dataset.kind).toBe("refused");
    expect(q(harness.app, `${row(5)} .outcome`).title).toBe("Nothing moved: already open.");
  });
});

describe("bulk", () => {
  it("moves the selected sessions in one request", async () => {
    const harness = await mount();
    await pick(harness.app, 4, 5);
    await click(q(harness.app, board(".bulk-bar")));
    expect(harness.posts()[0]).toMatchObject({ body: { ids: [sid(4), sid(5)] }, url: "/api/sessions/handoff" });
    expect(harness.app.querySelector(".bulk-count")).toBeNull();
  });

  it("is disabled with the first blocked row's reason when any selected row cannot move", async () => {
    const { app } = await mount();
    await pick(app, 4, 1);
    const button = q<HTMLButtonElement>(app, board(".bulk-bar"));
    expect(button.disabled).toBe(true);
    expect(button.title).toBe(make(1).move_reason);
  });

  it("is capped at five, like resume", async () => {
    const rows = [...sessionRows(), make(9, { group: 2, movable: true, move_reason: null, status: "untagged" })];
    const many = rows.map((session) => (session.done ? session : { ...session, movable: true, move_reason: null }));
    const { app } = await mount("", { rows: many });
    await pick(app, 1, 2, 3, 4, 5, 9);
    const button = q<HTMLButtonElement>(app, board(".bulk-bar"));
    expect(button.disabled).toBe(true);
    expect(button.getAttribute("aria-label")).toBe("at most 5 sessions at once");
  });
});
