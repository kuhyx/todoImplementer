/** Tiny element builder. Text goes in via textContent only: notes, diffs and feeds are untrusted. */

export type Child = false | Node | null | string | undefined;
type AttributeValue = boolean | null | number | string | undefined;
type Handlers = { [K in keyof HTMLElementEventMap]?: (event: HTMLElementEventMap[K]) => void };

export interface Props {
  attrs?: Record<string, AttributeValue>;
  class?: string;
  on?: Handlers;
  text?: string;
}

const ABSENT = new Set<AttributeValue>([false, null, undefined]);

function setAttribute(element: HTMLElement, name: string, value: AttributeValue): void {
  if (typeof value === "boolean" && name.startsWith("aria-")) {
    element.setAttribute(name, String(value));
    return;
  }
  if (ABSENT.has(value)) return;
  element.setAttribute(name, value === true ? "" : String(value));
}

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Props = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (props.class !== undefined) element.className = props.class;
  if (props.text !== undefined) element.textContent = props.text;
  if ((props.attrs) != null) {
    for (const [name, value] of Object.entries(props.attrs)) setAttribute(element, name, value);
  }
  if ((props.on) != null) {
    for (const [name, handler] of Object.entries(props.on)) {
      element.addEventListener(name, handler as EventListener);
    }
  }
  for (const child of children) {
    if (child !== false && child !== null && child !== undefined) element.append(child);
  }
  return element;
}

/** Typed `querySelector` that fails loudly: a missing node is a bug, not a no-op. */
export function must<T extends Element>(root: ParentNode, selector: string): T {
  const found = root.querySelector<T>(selector);
  if (found === null) throw new Error(`missing element: ${selector}`);
  return found;
}
