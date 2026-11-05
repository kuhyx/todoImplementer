import { beforeEach, describe, expect, it } from "vitest";

import { memoryContext } from "@/usage/context";
import { fixtures } from "@/usage/fixtures/load";
import { sessionsPanel } from "@/usage/schemas";
import { makeTable } from "@/usage/table-element";
import { type Column, PAGE, type Row } from "@/usage/table-model";

const sessions = sessionsPanel.parse(fixtures.sessions).sessions as unknown as Row[];
const columns: Column[] = [
  { href: (row) => `#/s/${String(row.key)}`, key: "title", kind: "text", label: "Title" },
  { key: "usd", kind: "number", label: "USD" },
  { key: "final_tag", kind: "enum", label: "Tag" },
  { key: "models", kind: "enum", label: "Models" },
  { key: "cwd", kind: "text", label: "Dir" },
];
const build = (rows: Row[] = sessions, hash = "") => {
  const context = memoryContext(hash);
  const table = makeTable({ columns, context, id: "t", rows, title: "Sessions" });
  document.body.replaceChildren(table);
  return { context, table };
};
const bodyRows = (table: Element): Element[] => [...table.querySelectorAll("tbody tr")];
const field = <T extends Element>(table: Element, selector: string): T => table.querySelector<T>(selector)!;
const type = (input: HTMLInputElement | HTMLSelectElement, value: string, event = "input"): void => {
  input.value = value;
  input.dispatchEvent(new Event(event));
};
const firstColumn = (table: Element): string[] => bodyRows(table).map((row) => row.querySelector("td")?.textContent ?? "");

beforeEach(() => {
  document.body.replaceChildren();
});

describe("usage-table", () => {
  it("renders real session rows with links and the count", () => {
    const { table } = build();
    expect(bodyRows(table)).toHaveLength(42);
    expect(field(table, ".ut-count").textContent).toBe("42 / 42");
    expect(field<HTMLAnchorElement>(table, "tbody a").getAttribute("href")).toMatch(/^#\/s\//v);
    expect(table.textContent).not.toMatch(/\[object Object\]|undefined|NaN/v);
    expect(field<HTMLButtonElement>(table, ".ut-bar .btn").hidden).toBe(true);
  });

  it("sorts on every column header and shows aria-sort", () => {
    const { context, table } = build();
    const reordered: boolean[] = [];
    for (const column of columns) {
      const head = field<HTMLElement>(table, `th[data-key="${column.key}"]`);
      const before = firstColumn(table).join("|");
      field<HTMLButtonElement>(head, "button").click();
      expect(head.getAttribute("aria-sort")).toBe("ascending");
      field<HTMLButtonElement>(head, "button").click();
      expect(head.getAttribute("aria-sort")).toBe("descending");
      if (column.kind !== "enum") reordered.push(firstColumn(table).join("|") !== before);
      field<HTMLButtonElement>(head, "button").click();
      expect(head.getAttribute("aria-sort")).toBe("none");
    }
    expect(reordered).toEqual([true, true, true]);
    field<HTMLButtonElement>(table, 'th[data-key="usd"] button').click();
    field<HTMLButtonElement>(table, 'th[data-key="title"] button').dispatchEvent(new MouseEvent("click", { shiftKey: true }));
    expect(context.hash()).toBe("t.t.sort=usd%2Ctitle");
  });

  it("orders usd high to low on a descending click", () => {
    const { table } = build();
    const usd = (): number[] => bodyRows(table).map((row) => Number((row as HTMLTableRowElement).cells[1]?.textContent.replace("$", "")));
    field<HTMLButtonElement>(table, 'th[data-key="usd"] button').click();
    field<HTMLButtonElement>(table, 'th[data-key="usd"] button').click();
    expect(usd()).toEqual(usd().toSorted((a, b) => b - a));
  });

  it("fuzzy-searches, filters by range, enum and text, and writes the hash", () => {
    const { context, table } = build();
    type(field(table, "input[type=search]"), "zzzzqq");
    expect(bodyRows(table)).toHaveLength(1);
    expect(table.querySelector(".ut-empty")?.textContent).toBe("No rows match.");
    type(field(table, "input[type=search]"), "");
    type(field(table, '[data-f="usd.min"]'), "1");
    type(field(table, '[data-f="usd.max"]'), "5");
    const matched = bodyRows(table).length;
    expect(matched).toBeLessThan(42);
    expect(field(table, ".ut-count").textContent).toContain(`${String(matched)} / ${String(matched)} (42)`);
    expect(context.hash()).toContain("t.t.f.usd=1..5");
    type(field(table, '[data-f="usd.min"]'), "");
    type(field(table, '[data-f="usd.max"]'), "");
    expect(context.hash()).not.toContain("usd");
    const tag = field<HTMLSelectElement>(table, 'select[data-f="final_tag"]');
    type(tag, "DONE", "change");
    expect(bodyRows(table).every((row) => (row as HTMLTableRowElement).cells[2]?.textContent === "DONE")).toBe(true);
    type(tag, "", "change");
    type(field(table, '[data-f="cwd"]'), "home");
    expect(context.hash()).toContain("f.cwd=%7Ehome");
    type(field(table, '[data-f="cwd"]'), "");
    expect(context.hash()).toBe("");
  });

  it("restores state from the hash and Reset clears it", () => {
    const { context, table } = build(sessions, "t.t.q=a&t.t.f.usd=1..&t.t.f.final_tag==DONE&t.t.f.cwd=~x&t.t.sort=-usd");
    expect(field<HTMLInputElement>(table, "input[type=search]").value).toBe("a");
    expect(field<HTMLSelectElement>(table, 'select[data-f="final_tag"]').value).toBe("DONE");
    expect(field<HTMLInputElement>(table, '[data-f="usd.min"]').value).toBe("1");
    expect(field<HTMLInputElement>(table, '[data-f="cwd"]').value).toBe("x");
    expect(field<HTMLElement>(table, 'th[data-key="usd"]').getAttribute("aria-sort")).toBe("descending");
    const reset = field<HTMLButtonElement>(table, ".ut-bar .btn");
    expect(reset.hidden).toBe(false);
    reset.click();
    expect(context.hash()).toBe("");
    expect(field<HTMLInputElement>(table, '[data-f="usd.min"]').value).toBe("");
    expect(field<HTMLInputElement>(table, "input[type=search]").value).toBe("");
    expect(bodyRows(table)).toHaveLength(42);
  });

  it("caps long tables at one page and shows all on request", () => {
    const many = Array.from({ length: PAGE + 50 }, (_, index) => ({ cwd: null, final_tag: null, models: {}, title: `row ${String(index)}`, usd: index }));
    const { context, table } = build(many);
    expect(bodyRows(table)).toHaveLength(PAGE);
    const more = [...table.querySelectorAll<HTMLButtonElement>(".ut-bar .btn")].find((button) => !button.hidden && button.textContent.startsWith("Show"));
    if (more === undefined) throw new Error("no show-all button");
    expect(more.textContent).toBe(`Show all ${String(PAGE + 50)}`);
    more.click();
    expect(bodyRows(table)).toHaveLength(PAGE + 50);
    expect(context.hash()).toBe("t.t.limit=0");
    expect(more.textContent).toBe(`Show first ${String(PAGE)}`);
    more.click();
    expect(bodyRows(table)).toHaveLength(PAGE);
  });

  it("uses a text filter for enum columns with too many values and registers once", () => {
    const wide = Array.from({ length: 40 }, (_, index) => ({ cwd: "x", final_tag: `tag ${String(index)}`, models: {}, title: "t", usd: 1 }));
    const { table } = build(wide);
    expect(table.querySelector('select[data-f="final_tag"]')).toBeNull();
    expect(table.querySelector('input[data-f="final_tag"]')).not.toBeNull();
    expect(customElements.get("usage-table")).toBeDefined();
  });
});
