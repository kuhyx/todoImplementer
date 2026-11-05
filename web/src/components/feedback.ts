/** Loader naming what it waits on, and toasts. The 1 s rule: a wait of 1 s or more always shows a loader. */
import { h } from "@/lib/dom";

export const SLOW_MS = 1000;

export function loader(text: string): HTMLElement {
  return h("p", { attrs: { role: "status" }, class: "loader" }, h("span", { attrs: { "aria-hidden": "true" }, class: "spinner" }), h("span", { text }));
}

function region(): HTMLElement {
  const found = document.querySelector<HTMLElement>("#toasts");
  if (found !== null) return found;
  const created = h("div", { attrs: { id: "toasts" }, class: "toasts" });
  document.body.append(created);
  return created;
}

export function showToast(text: string, kind: "error" | "info" = "info"): void {
  // The same message while its toast is still up adds nothing: a stream of bad frames must not stack N copies.
  if ([...region().children].some((toast) => toast.textContent === text)) return;
  const toast = h("button", {
    attrs: { role: kind === "error" ? "alert" : "status", type: "button" },
    class: `toast toast-${kind}`,
    on: {
      click: () => {
        toast.remove();
      },
    },
    text,
  });
  region().append(toast);
  setTimeout(() => {
    toast.remove();
  }, kind === "error" ? 12_000 : 4000);
}
