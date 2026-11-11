import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { make, sid } from "#fixtures/fixture-sessions";
import { click, ids, install, mount, q, qa, setToken, uninstall, useClipboard } from "#fixtures/sessions-harness";
import { ARMED_MS, COPIED_MS } from "@/sessions/parts";

beforeEach(install);
afterEach(uninstall);

const row = (id: number): string => `tr[data-id="${sid(id)}"]`;
const pick = async (app: Element, ...numbers: number[]): Promise<void> => {
  for (const number_ of numbers) await click(q(app, `${row(number_)} input[type="checkbox"]`));
};
const glyph = (app: Element): HTMLElement => q(app, ".outcome");

describe("selection", () => {
  it("selects rows, ranges with shift, all, and clears", async () => {
    const { app } = await mount();
    await pick(app, 1);
    expect(q(app, ".bulk-count").textContent).toBe("1");
    await click(q(app, `${row(4)} input[type="checkbox"]`), { shiftKey: true });
    expect(q(app, ".bulk-count").textContent).toBe("4");
    await pick(app, 2);
    expect(q(app, ".bulk-count").textContent).toBe("3");
    await click(q(app, 'thead input[type="checkbox"]'));
    expect(q(app, ".bulk-count").textContent).toBe("5");
    expect(q<HTMLInputElement>(app, 'thead input[type="checkbox"]').checked).toBe(true);
    await click(q(app, 'thead input[type="checkbox"]'));
    expect(app.querySelector(".bulk-bar")).toBeNull();
    await pick(app, 3);
    await click(q(app, 'button[aria-label="clear the selection"]'));
    expect(app.querySelector(".bulk-bar")).toBeNull();
  });

  it("a shift click with no anchor selects just that row", async () => {
    const { app } = await mount();
    await click(q(app, `${row(3)} input[type="checkbox"]`), { shiftKey: true });
    expect(q(app, ".bulk-count").textContent).toBe("1");
  });
});

describe("one session", () => {
  it("marks done with the token, then reloads the list", async () => {
    const harness = await mount();
    await click(q(harness.app, `${row(1)} button[aria-label="mark done"]`));
    expect(harness.posts()).toEqual([{ body: { id: sid(1), mark: "done" }, headers: { "Content-Type": "application/json", "X-Todoimpl-Token": "tok" }, url: "/api/sessions/mark" }]);
    expect(harness.stub.calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    expect(glyph(harness.app).dataset.kind).toBe("ok");
    expect(glyph(harness.app).title).toBe("Done.");
    expect(glyph(harness.app).textContent).toBe("");
  });

  it("offers unmark only for a hand mark and nothing for a session that tagged itself done", async () => {
    const { app } = await mount("#done=1");
    expect(app.querySelector(`${row(6)} button[aria-label="remove the done mark"]`)).not.toBeNull();
    expect(app.querySelector(`${row(6)} button[aria-label="mark done"]`)).toBeNull();
    expect(app.querySelector(`${row(7)} button[aria-label="mark done"]`)).toBeNull();
    expect(app.querySelector(`${row(7)} button[aria-label="remove the done mark"]`)).toBeNull();
  });

  it("unmarks with a null mark", async () => {
    const harness = await mount("#done=1");
    await click(q(harness.app, `${row(6)} button[aria-label="remove the done mark"]`));
    expect(harness.posts()[0]?.body).toEqual({ id: sid(6), mark: null });
  });

  it("resumes in a terminal without reloading, and the button is the one a phone hides", async () => {
    const harness = await mount();
    const button = q(harness.app, `${row(1)} button[aria-label="resume in a terminal"]`);
    expect(button.classList.contains("desktop-only")).toBe(true);
    expect(q(harness.app, `${row(1)} button[aria-label="copy the resume command"]`).classList.contains("desktop-only")).toBe(false);
    await click(button);
    expect(harness.posts()[0]).toMatchObject({ body: { id: sid(1) }, url: "/api/sessions/resume" });
    expect(harness.stub.calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
  });

  it("shows a refusal as a lock and a failed attempt as a warning, with the server's words in the title", async () => {
    const refused = await mount("", { reply: { argv: [], ok: false, refused: true, stderr: "kept", stdout: "", summary: "Nothing moved." } });
    await click(q(refused.app, `${row(1)} button[aria-label="resume in a terminal"]`));
    expect(glyph(refused.app).dataset.kind).toBe("refused");
    expect(glyph(refused.app).title).toBe("Nothing moved.\nkept");
    document.body.replaceChildren();
    const failed = await mount("", { reply: { argv: [], ok: false, refused: false, stderr: "", stdout: "", summary: "Could not." } });
    await click(q(failed.app, `${row(1)} button[aria-label="resume in a terminal"]`));
    expect(glyph(failed.app).dataset.kind).toBe("failed");
  });

  it("shows a rejected request (403, down) as a warning", async () => {
    const harness = await mount("", { reply: new Error("down") });
    await click(q(harness.app, `${row(1)} button[aria-label="resume in a terminal"]`));
    expect(glyph(harness.app).dataset.kind).toBe("failed");
    expect(glyph(harness.app).title).toContain("cannot reach");
  });

  it("does not send anything when the page has no CSRF token", async () => {
    const harness = await mount();
    setToken(null);
    await click(q(harness.app, `${row(1)} button[aria-label="mark done"]`));
    expect(harness.posts()).toEqual([]);
    expect(glyph(harness.app).dataset.kind).toBe("failed");
  });

  it("deletes in two clicks: the first arms with a number, the second sends; it disarms by itself", async () => {
    const harness = await mount();
    const trash = (): HTMLButtonElement => q(harness.app, `${row(1)} button[aria-label^="move to the trash"], ${row(1)} button[data-armed]`);
    await click(trash());
    expect(trash().dataset.armed).toBe("true");
    expect(q(trash(), ".armed-count").textContent).toBe("1");
    expect(harness.posts()).toEqual([]);
    await vi.advanceTimersByTimeAsync(ARMED_MS);
    expect(trash().dataset.armed).toBeUndefined();
    await click(trash());
    await click(trash());
    expect(harness.posts()[0]).toMatchObject({ body: { id: sid(1) }, url: "/api/sessions/delete" });
  });

  it("copies the resume command and flashes a check, then the copy glyph again", async () => {
    const write = useClipboard();
    const { app } = await mount();
    const button = q(app, `${row(1)} button[aria-label="copy the resume command"]`);
    await click(button);
    expect(write).toHaveBeenCalledWith(make(1).resume_command);
    expect(button.querySelector("path")?.getAttribute("d")).toBe("M5 12.5l4.5 4.5L19 7.5");
    await vi.advanceTimersByTimeAsync(COPIED_MS);
    expect(button.querySelector("path")?.getAttribute("d")).toContain("M9 9h11v11H9z");
  });

  it("flashes a warning when the clipboard refuses", async () => {
    useClipboard(vi.fn().mockRejectedValue(new Error("blocked")));
    const { app } = await mount();
    const button = q(app, `${row(1)} button[aria-label="copy the resume command"]`);
    await click(button);
    expect(button.getAttribute("aria-label")).toBe("the clipboard is not available");
  });
});

describe("a selection", () => {
  it("marks done, unmarks, and clears the selection after a success", async () => {
    const harness = await mount();
    await pick(harness.app, 1, 3);
    await click(q(harness.app, '.bulk-bar button[aria-label="mark done"]'));
    expect(harness.posts()[0]?.body).toEqual({ ids: [sid(1), sid(3)], mark: "done" });
    expect(harness.app.querySelector(".bulk-count")).toBeNull();
    expect(glyph(harness.app).dataset.kind).toBe("ok");
    await click(q(harness.app, '.bulk-bar button[aria-label="clear the selection"]'));
    expect(harness.app.querySelector(".bulk-bar")).toBeNull();
    await pick(harness.app, 2);
    await click(q(harness.app, '.bulk-bar button[aria-label="remove the done mark"]'));
    expect(harness.posts()[1]?.body).toEqual({ ids: [sid(2)], mark: null });
  });

  it("keeps the selection when the server refuses", async () => {
    const harness = await mount("", { reply: { argv: [], ok: false, refused: true, stderr: "", stdout: "", summary: "Nothing moved." } });
    await pick(harness.app, 1);
    await click(q(harness.app, '.bulk-bar button[aria-label="move to the trash"]'));
    await click(q(harness.app, '.bulk-bar button[data-armed]'));
    expect(harness.posts()[0]).toMatchObject({ body: { ids: [sid(1)] }, url: "/api/sessions/delete" });
    expect(q(harness.app, ".bulk-count").textContent).toBe("1");
    expect(glyph(harness.app).dataset.kind).toBe("refused");
  });

  it("resumes up to five and disables the button above that, with the reason in its title", async () => {
    const harness = await mount("#done=1");
    await pick(harness.app, 1, 2, 3);
    await click(q(harness.app, '.bulk-bar button[aria-label="resume in a terminal"]'));
    expect(harness.posts()[0]).toMatchObject({ body: { ids: [sid(1), sid(2), sid(3)] }, url: "/api/sessions/resume" });
    await pick(harness.app, 4, 5, 6);
    const resume = q<HTMLButtonElement>(harness.app, ".bulk-bar .desktop-only");
    expect(resume.disabled).toBe(true);
    expect(resume.title).toBe("at most 5 terminals at once");
  });

  it("copies every selected command, one per line", async () => {
    const write = useClipboard();
    const { app } = await mount();
    await pick(app, 3, 1);
    await click(q(app, '.bulk-bar button[aria-label="copy the resume commands"]'));
    expect(write).toHaveBeenCalledWith(`${make(1).resume_command}\n${make(3).resume_command}`);
  });

  it("keeps an answer waiting with nothing selected until it is dismissed", async () => {
    const harness = await mount("", { reply: { argv: [], ok: false, refused: false, stderr: "", stdout: "", summary: "Could not." } });
    await pick(harness.app, 1);
    await click(q(harness.app, '.bulk-bar button[aria-label="resume in a terminal"]'));
    await pick(harness.app, 1);
    expect(harness.app.querySelector(".bulk-count")).toBeNull();
    expect(glyph(harness.app).dataset.kind).toBe("failed");
    expect(qa(harness.app, ".bulk-bar button")).toHaveLength(1);
    await click(q(harness.app, '.bulk-bar button[aria-label="clear the selection"]'));
    expect(harness.app.querySelector(".bulk-bar")).toBeNull();
    expect(ids(harness.app)).toHaveLength(5);
  });
});
