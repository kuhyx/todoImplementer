/** A QR code as one SVG path (modules as row runs). Built with createElementNS: no markup string, so the page CSP stays untouched. */
import { encode } from "uqr";

const NS = "http://www.w3.org/2000/svg";
const QUIET_ZONE = 4;

/** `M x y h<run> v1 h-<run> z` for every horizontal run of dark modules. */
function runs(rows: readonly (readonly boolean[])[]): string {
  const parts: string[] = [];
  for (const [y, row] of rows.entries()) {
    let start = -1;
    for (const [x, isDark] of [...row, false].entries()) {
      if (isDark) {
        if (start < 0) start = x;
        continue;
      }
      if (start < 0) continue;
      parts.push(`M${String(start)} ${String(y)}h${String(x - start)}v1h-${String(x - start)}z`);
      start = -1;
    }
  }
  return parts.join("");
}

/** Colours come from the `.qr-bg` / `.qr-fg` classes (phone.css): dark on light in either colour scheme, which scanners need. */
export function qrSvg(text: string, label: string): SVGSVGElement {
  const { data, size } = encode(text, { border: QUIET_ZONE, ecc: "M" });
  const svg = document.createElementNS(NS, "svg");
  const field = document.createElementNS(NS, "rect");
  const modules = document.createElementNS(NS, "path");
  svg.setAttribute("viewBox", `0 0 ${String(size)} ${String(size)}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label);
  svg.setAttribute("class", "phone-qr");
  svg.setAttribute("shape-rendering", "crispEdges");
  field.setAttribute("class", "qr-bg");
  field.setAttribute("width", String(size));
  field.setAttribute("height", String(size));
  modules.setAttribute("class", "qr-fg");
  modules.setAttribute("d", runs(data));
  svg.append(field, modules);
  return svg;
}
