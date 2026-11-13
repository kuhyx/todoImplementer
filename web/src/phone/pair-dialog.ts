/** The pairing modal: QR of a one-time link, a countdown ring, a fresh code when it expires. Numbers and glyphs only; names live in aria-label/title. */
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { mintPair, type Pair } from "@/phone/pair-api";
import { phoneButton } from "@/phone/phone-button";
import { qrSvg } from "@/phone/qr";

export const TICK_MS = 1000;
const NS = "http://www.w3.org/2000/svg";
const RADIUS = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const TITLE = "Pair a phone";

function ring(): { element: HTMLElement; set: (left: number, fraction: number) => void } {
  const svg = document.createElementNS(NS, "svg");
  const track = document.createElementNS(NS, "circle");
  const arc = document.createElementNS(NS, "circle");
  svg.setAttribute("viewBox", "0 0 48 48");
  svg.setAttribute("aria-hidden", "true");
  for (const [circle, kind] of [[track, "track"], [arc, "arc"]] as const) {
    circle.setAttribute("class", `ring-${kind}`);
    circle.setAttribute("cx", "24");
    circle.setAttribute("cy", "24");
    circle.setAttribute("r", String(RADIUS));
  }
  arc.setAttribute("stroke-dasharray", String(CIRCUMFERENCE));
  svg.append(track, arc);
  const digits = h("span", { class: "ring-digits" });
  const element = h("div", { attrs: { role: "timer" }, class: "phone-ring" }, svg, digits);
  return {
    element,
    set: (left, fraction) => {
      digits.textContent = String(left);
      arc.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE * (1 - fraction)));
    },
  };
}

/** Opens the modal. `mint` is injectable for tests; it is called again each time the shown link expires. */
export function openPairDialog(opener: HTMLElement | null, mint: () => Promise<Pair> = mintPair): void {
  let isClosed = false;
  let run = 0;
  let timer: ReturnType<typeof setInterval> | undefined;
  const stage = h("div", { class: "phone-stage" });
  const countdown = ring();
  const close = (): void => {
    isClosed = true;
    clearInterval(timer);
    document.removeEventListener("keydown", onKey);
    backdrop.remove();
    opener?.focus();
  };
  const closeButton = phoneButton("close", "Close", "close", close);
  const card = h("div", { attrs: { "aria-label": TITLE, "aria-modal": "true", role: "dialog" }, class: "phone-card" }, stage, countdown.element, closeButton);
  const backdrop = h("div", { class: "phone-backdrop", on: { click: (event) => { if (event.target === backdrop) close(); } } }, card);
  function onKey(event: KeyboardEvent): void {
    if (event.key === "Escape") close();
  }

  const spinner = (): HTMLElement => h("div", { attrs: { "aria-label": TITLE, role: "status" }, class: "phone-spin" });
  const warning = (error: unknown): HTMLElement => {
    const text = errorText(error);
    const button = phoneButton("failed", text, "warn", () => { void load(); });
    button.classList.add("phone-warn");
    return button;
  };

  async function load(): Promise<void> {
    const mine = ++run;
    clearInterval(timer);
    countdown.element.hidden = true;
    stage.replaceChildren(spinner());
    try {
      const pair = await mint();
      if (isClosed || mine !== run) return;
      const total = Math.max(1, pair.expires_at - Date.now() / 1000);
      const paint = (): void => {
        const left = pair.expires_at - Date.now() / 1000;
        if (left <= 0) {
          void load();
          return;
        }
        countdown.set(Math.ceil(left), Math.min(1, left / total));
      };
      stage.replaceChildren(qrSvg(pair.url, TITLE));
      countdown.element.hidden = false;
      paint();
      timer = setInterval(paint, TICK_MS);
    } catch (error) {
      if (isClosed || mine !== run) return;
      stage.replaceChildren(warning(error));
    }
  }

  document.addEventListener("keydown", onKey);
  document.body.append(backdrop);
  closeButton.focus();
  void load();
}
