/** Shared harness for the <ti-new-task> tests: mount, fill, query and file events. */
import { vi } from "vitest";

import { TiNewTask } from "@/components/new-task";
import { makeCards } from "@/test/fixtures";
import { stubFetch } from "@/test/net";

export const [card] = makeCards();
export const OK = { note: "abcd1234", ok: true, started: true, task: card };
export const q = <T extends Element = HTMLElement>(root: ParentNode, sel: string): T => {
  const found = root.querySelector<T>(sel);
  if (found === null) throw new Error(`no ${sel}`);
  return found;
};
export const image = (name = "a.png"): File => new File(["px"], name, { type: "image/png" });
export const pdf = (name = "spec.pdf", type = "application/pdf"): File => new File(["%PDF"], name, { type });
export const sized = (name: string, size: number): File => {
  const file = pdf(name);
  Object.defineProperty(file, "size", { value: size });
  return file;
};
export const UP = (id: string): Record<string, unknown> => ({ ok: true, upload: { id, name: "x", size: 1 } });
export const ids = ["a", "b", "c"].map((c) => c.repeat(32));

export function mount(routes_: Record<string, unknown> = {}): TiNewTask {
  stubFetch(routes_);
  const element = new TiNewTask();
  document.body.append(element);
  element.repos = ["kuhyx/demo", "kuhyx/other"];
  return element;
}

/** Taps the chooser: "none", "all" or a repo name per entry, opening the folded row first when needed. */
export function choose(element: TiNewTask, ...picks: string[]): void {
  for (const pick of picks) {
    const folded = element.querySelector<HTMLButtonElement>("[data-new-task=scope]:not([hidden])");
    folded?.click();
    const sel = pick === "none" || pick === "all" ? `[data-scope=${pick}]` : `[data-repo="${pick}"]`;
    q<HTMLButtonElement>(element, sel).click();
  }
}

/** Picks `repos` (none when empty) and types `text` into the one description box. */
export function fill(element: TiNewTask, text = "Fix it\nsee pic", repos: readonly string[] = ["kuhyx/demo"]): void {
  choose(element, ...repos);
  const field = q<HTMLTextAreaElement>(element, "textarea[name=body]");
  field.value = text;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

export const submit = (element: TiNewTask): HTMLButtonElement => q<HTMLButtonElement>(element, "[data-new-task=submit]");
export const panel = (element: TiNewTask): HTMLElement => q(element, ".nt-panel");

export function filesEvent(type: "drop" | "paste", files: File[]): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, type === "paste" ? "clipboardData" : "dataTransfer", { value: { files } });
  return event;
}


export function setUp(define: () => void): void {
  vi.useFakeTimers();
  let made = 0;
  URL.createObjectURL = vi.fn(() => {
    made += 1;
    return `blob:${String(made)}`;
  });
  URL.revokeObjectURL = vi.fn();
  localStorage.clear(); // a draft of the last test must not come back (T2493)
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok">';
  document.body.replaceChildren();
  define();
  define();
}

export function tearDown(): void {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
}
