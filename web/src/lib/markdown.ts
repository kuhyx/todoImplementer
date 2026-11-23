/**
 * Just enough Markdown for plan.md and the live-check report: headings, bullets (with checkboxes),
 * numbered lists, fenced code, paragraphs and `inline code`. Everything is built with textContent,
 * so nothing in the note can inject markup.
 */
import { type Child, h } from "@/lib/dom";

interface State {
  code: null | string[];
  list: HTMLElement | null;
  root: HTMLElement;
}

/** Plain text with `**bold**` spans turned into <strong> nodes; a lone `**` or one next to a space stays as it is (T2525). */
function bold(text: string): Child[] {
  return text.split(/(\*\*[^*\s](?:[^*]*[^*\s])?\*\*)/v).flatMap((part, index): Child[] => {
    if (part === "") return [];
    return [index % 2 === 1 ? h("strong", { text: part.slice(2, -2) }) : part];
  });
}

/** Text with `code` and `**bold**` spans turned into <code> and <strong> nodes; also used by the question body. */
export function inline(text: string): Child[] {
  return text.split(/(`[^`]+`)/v).flatMap((part): Child[] => {
    if (part === "") return [];
    return part.startsWith("`") ? [h("code", { text: part.slice(1, -1) })] : bold(part);
  });
}

function heading(line: string): HTMLElement | null {
  const marker = /^#{1,3}(?=\s)/v.exec(line);
  if (marker === null) return null;
  const level = String(marker[0].length + 2) as "3" | "4" | "5";
  return h(`h${level}`, { class: "md-h" }, ...inline(line.slice(marker[0].length).trim()));
}

function listItem(line: string): null | { ordered: boolean; text: string } {
  const bullet = /^\s*[\-*]\s+/v.exec(line);
  if (bullet !== null) return { ordered: false, text: line.slice(bullet[0].length) };
  const numbered = /^\s*\d+\.\s+/v.exec(line);
  return numbered === null ? null : { ordered: true, text: line.slice(numbered[0].length) };
}

function checkbox(text: string): Child[] {
  const box = /^\[[ xX]\]\s+/v.exec(text);
  if (box === null) return inline(text);
  const isDone = !box[0].startsWith("[ ]");
  const mark = h("span", { class: isDone ? "md-check done" : "md-check", text: isDone ? "done" : "open" });
  return [mark, ...inline(text.slice(box[0].length))];
}

function listFor(state: State, tag: "ol" | "ul"): HTMLElement {
  if (state.list?.tagName.toLowerCase() === tag) return state.list;
  const created = h(tag, { class: "md-list" });
  state.root.append(created);
  return created;
}

const codeBlock = (lines: string[]): HTMLElement => h("pre", { class: "md-code", text: lines.join("\n") });

function fence(state: State): void {
  if (state.code !== null) state.root.append(codeBlock(state.code));
  state.code = state.code === null ? [] : null;
  state.list = null;
}

function textLine(state: State, line: string): void {
  const item = listItem(line);
  if (item !== null) {
    state.list = listFor(state, item.ordered ? "ol" : "ul");
    state.list.append(h("li", {}, ...checkbox(item.text)));
    return;
  }
  state.list = null;
  const head = heading(line);
  if (head !== null) state.root.append(head);
  else if (line.trim() !== "") state.root.append(h("p", {}, ...inline(line)));
}

export function renderMarkdown(source: string): HTMLElement {
  const state: State = { code: null, list: null, root: h("div", { class: "md" }) };
  for (const line of source.split("\n")) {
    if (line.startsWith("```")) fence(state);
    else if (state.code === null) textLine(state, line);
    else state.code.push(line);
  }
  if (state.code !== null) state.root.append(codeBlock(state.code));
  return state.root;
}
