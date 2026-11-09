import type { Credits } from "@/lib/schemas-common";

/**
 * The global "Fall back to free API credits" switch. The server words `credits.text` and
 * `credits.state`; the page shows them, POSTs the flipped value and lets the next board
 * answer decide what shows (no guess). State lives at module level so the 3 s board repaint
 * keeps the in-flight, loader and error display.
 */
import { loader, SLOW_MS } from "@/components/feedback";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText, postCreditsFallback } from "@/lib/http";

const LABEL = "Fall back to free API credits";
interface Flight {
  current: HTMLElement | null;
  error: null | string;
  latest: null | { credits: Credits; onDone: () => void };
  pending: boolean;
  slow: boolean;
}
const flight: Flight = { current: null, error: null, latest: null, pending: false, slow: false };

function paint(host: HTMLElement, credits: Credits, onDone: () => void): void {
  const box = h("input", {
    attrs: { "aria-busy": flight.pending, disabled: flight.pending, name: "credits-fallback", type: "checkbox" },
    on: { change: () => { void flip(!credits.enabled, onDone); } },
  });
  box.checked = credits.enabled;
  host.replaceChildren(...[
    h("label", { class: "credits-label" }, box, LABEL),
    h("span", { attrs: { "data-state": credits.state }, class: "credits-text", text: credits.text }),
    flight.pending && flight.slow && loader(`Waiting for the server to save: ${LABEL}`),
    flight.error !== null && h("span", { attrs: { role: "alert" }, class: "credits-error", text: flight.error }),
  ].filter((child) => child !== false));
}

async function flip(isEnabled: boolean, onDone: () => void): Promise<void> {
  const csrf = csrfToken();
  flight.error = null;
  if (csrf === null) {
    flight.error = "This page has no CSRF token; reload it.";
    redraw();
    return;
  }
  flight.pending = true;
  flight.slow = false;
  redraw();
  const timer = setTimeout(() => { flight.slow = true; redraw(); }, SLOW_MS);
  try {
    await postCreditsFallback(isEnabled, csrf);
  } catch (error) {
    flight.error = errorText(error);
  }
  clearTimeout(timer);
  flight.pending = false;
  flight.slow = false;
  redraw();
  onDone();
}

function redraw(): void {
  if (flight.current !== null && flight.latest !== null) paint(flight.current, flight.latest.credits, flight.latest.onDone);
}

export function renderCreditsToggle(credits: Credits, onDone: () => void): HTMLElement {
  const host = h("div", { class: "credits-toggle" });
  flight.current = host;
  flight.latest = { credits, onDone };
  paint(host, credits, onDone);
  return host;
}
