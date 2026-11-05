/** SVG builder: attributes only, because presentation attributes pass the `default-src 'self'` CSP and a `style` attribute would not. */
export function svg<K extends keyof SVGElementTagNameMap>(tag: K, attributes: Record<string, number | string> = {}, ...children: (Node | string)[]): SVGElementTagNameMap[K] {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  node.append(...children);
  return node;
}
