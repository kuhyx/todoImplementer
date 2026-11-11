/** The note's `ask` block as buttons: options, one Take-recommended, RUN / add-and-run, screenshot verdict, Undo.
 * A click shows its result at once (local state), then POSTs; the drawer's next poll replaces it with the server's. */
import type { TaskDetail } from "@/lib/schemas";
import type { AskItem, AskVerb } from "@/lib/schemas-asks";

import { showToast } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { postAsk } from "@/lib/asks-api";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { routes } from "@/lib/routes";

const OPEN = new Set<AskItem["state"]>(["open", "rejected"]);

interface Context {
  id: string;
  paint: () => void;
  root: HTMLElement;
  rows: AskItem[];
}

async function click(context: Context, verb: AskVerb, body: Record<string, unknown>, apply: (row: AskItem) => void): Promise<void> {
  const csrf = csrfToken();
  if (csrf === null) {
    showToast("This page has no CSRF token. Reload it from the server.", "error");
    return;
  }
  const ask = typeof body.ask === "string" ? body.ask : null;
  const row = context.rows.find((candidate) => candidate.id === ask);
  const before = context.rows.map((candidate) => ({ ...candidate }));
  if (verb === "take-recommended") {
    for (const open of context.rows) {
      if (open.type === "choice" && OPEN.has(open.state)) apply(open);
    }
  } else if (row !== undefined) apply(row);
  context.paint();
  try {
    const result = await postAsk(context.id, verb, body, csrf);
    if (result !== undefined && row !== undefined) {
      row.result = result;
      context.paint();
    }
    context.root.dispatchEvent(new CustomEvent("task-changed", { bubbles: true }));
  } catch (error) {
    context.rows.splice(0, context.rows.length, ...before);
    context.paint();
    showToast(errorText(error), "error");
  }
}

const copy = (text: string): void => {
  void navigator.clipboard.writeText(text).catch(() => {
    showToast(`Copy was blocked here. Command: ${text}`, "error");
  });
};

function choice(context: Context, row: AskItem): HTMLElement {
  const picked = row.answer;
  const buttons = (row.options ?? []).map((option) => {
    return h("button", {
      attrs: { "aria-pressed": picked === option, "data-option": option, disabled: !OPEN.has(row.state), type: "button" },
      class: `btn${option === row.recommended ? " btn--primary" : ""}`,
      on: { click: () => void click(context, "answer", { ask: row.id, option }, (r) => { r.answer = option; r.state = "answered"; }) },
      text: option,
    });
  },
  );
  const undo = row.state === "auto"
    ? iconButton("retry", "Undo", { "data-undo": row.id }, () => void click(context, "undo", { ask: row.id }, (r) => { r.state = "open"; delete r.answer; }))
    : null;
  return h("div", { attrs: { "data-ask": row.id, "data-state": row.state }, class: "ask-row" }, h("p", { class: "ask-title", text: row.title }), ...buttons, undo);
}

function command(context: Context, row: AskItem): HTMLElement {
  const text = row.command ?? "";
  const run = (isAdding: boolean) => {
    return (): void => {
      void click(context, "run", { add: isAdding, ask: row.id }, (r) => { r.state = "done"; });
    };
  };
  const button =
    row.mode === "terminal"
      ? [iconButton("failed", "Run in a terminal yourself", { "data-warning": true }, () => { copy(text); }), iconButton("copy", "Copy", { "data-copy": true }, () => { copy(text); })]
      : [iconButton(row.mode === "run" ? "running" : "plus", row.mode === "run" ? "Run" : "Add to allow-list and run", { "data-run": row.mode ?? "add_run" }, run(row.mode === "add_run"))];
  const result = row.result;
  const out = result === undefined ? null : h("pre", { attrs: { "data-exit": result.exit }, class: "ask-out", text: `${result.tail}\nexit ${String(result.exit)}${result.capped ? " (60 s cap)" : ""}`.trim() });
  return h("div", { attrs: { "data-ask": row.id, "data-state": row.state }, class: "ask-row" }, h("code", { text }), ...button, out);
}

function screenshot(context: Context, row: AskItem): HTMLElement {
  const img = row.shot === undefined ? null : h("img", { attrs: { alt: row.title, src: routes.shot(context.id, row.shot) }, class: "ask-shot" });
  const isOpen = OPEN.has(row.state);
  const set = (verb: "approve" | "reject", state: AskItem["state"]) => {
    return (): void => {
      void click(context, verb, { ask: row.id }, (r) => { r.state = state; });
    };
  };
  return h(
    "div",
    { attrs: { "data-ask": row.id, "data-state": row.state }, class: "ask-row" },
    h("p", { class: "ask-title", text: row.title }),
    img,
    isOpen ? iconButton("check", "Approve", { "data-approve": true }, set("approve", "approved")) : null,
    isOpen ? iconButton("close", "Reject", { "data-reject": true }, set("reject", "rejected")) : null,
  );
}

function draw(context: Context, row: AskItem): HTMLElement {
  if (row.type === "choice") return choice(context, row);
  return row.type === "command" ? command(context, row) : screenshot(context, row);
}

export function renderAskItems(detail: TaskDetail): HTMLElement | null {
  if (detail.ask_items.length === 0) return null;
  const root = h("section", { attrs: { "data-asks": true }, class: "asks" });
  const rows = detail.ask_items.map((item) => ({ ...item }));
  const context: Context = { id: detail.card.id, paint: () => { paint(); }, root, rows };
  const paint = (): void => {
    const body = rows.map((row) => draw(context, row));
    const isSeveral = rows.some((row) => row.type === "choice" && OPEN.has(row.state));
    const take = isSeveral
      ? iconButton("check", "Take recommended", { "data-take": true }, () => void click(context, "take-recommended", {}, (r) => { r.answer = r.recommended ?? ""; r.state = "answered"; }))
      : null;
    root.replaceChildren(...body, ...(take === null ? [] : [take]));
  };
  paint();
  return root;
}
