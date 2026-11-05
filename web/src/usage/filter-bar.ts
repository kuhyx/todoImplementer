import type { TokensIndex } from "@/usage/schemas";

import { h } from "@/lib/dom";
import { FILTER_KEYS } from "@/usage/api";
import { label } from "@/usage/labels";

type Key = (typeof FILTER_KEYS)[number];

const SCOPES = ["all", "main", "sub"] as const;

function field(name: string, control: HTMLElement): HTMLElement {
  return h("label", { class: "field" }, h("span", { class: "field-label", text: name }), control);
}

function select(key: Key, name: string, values: readonly string[], current: string, emptyLabel: string): HTMLElement {
  const known = current === "" || values.includes(current) ? values : [...values, current];
  return field(name, h("select", { attrs: { "data-filter": key, name: key } }, h("option", { attrs: { selected: current === "", value: "" }, text: emptyLabel }), ...known.map((value) => h("option", { attrs: { selected: value === current, value }, text: value }))));
}

/** Global filters; they travel in the hash with the table state and are sent with every panel request. */
export function filterBar(index: TokensIndex, parameters: URLSearchParams, onChange: (key: Key, value: string) => void): HTMLElement {
  const value = (key: Key): string => parameters.get(key) ?? "";
  const date = (key: "from" | "to", name: string): HTMLElement =>
    field(name, h("input", { attrs: { "data-filter": key, name: key, type: "date", value: value(key) } }));
  const bar = h(
    "div",
    { attrs: { role: "group" }, class: "filters" },
    select("scope", label.scope, SCOPES, value("scope") === "" ? "all" : value("scope"), label.all),
    select("cwd", label.directory, index.options.cwds, value("cwd"), label.all),
    select("model", label.model, index.options.models, value("model"), label.all),
    select("window", label.window, index.coverage.snapshots, value("window"), label.none),
    date("from", label.from),
    date("to", label.to),
  );
  bar.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    onChange(target.dataset.filter as Key, target.value);
  });
  return bar;
}
