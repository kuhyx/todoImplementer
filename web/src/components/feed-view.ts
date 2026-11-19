import type { LiveState } from "@/lib/live-feed";
import type { ActivityEvent } from "@/lib/schemas";

/** Live activity feed, newest line on top. Replayed events (same seq after a reconnect) are ignored; old lines drop past the cap. */
import { h } from "@/lib/dom";

export const FEED_CAP = 500;
const LONG_TEXT = 400;

const STATE_TEXT: Record<LiveState, string> = {
  closed: "stream ended",
  connecting: "connecting to the live stream…",
  live: "live",
  reconnecting: "connection lost, reconnecting…",
};

export interface Feed {
  append: (event: ActivityEvent) => void;
  el: HTMLElement;
  setState: (state: LiveState) => void;
}

/** HH:MM:SS in the viewer's own timezone (the server sends epoch seconds, UTC). */
function clock(epoch: number): string {
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", hourCycle: "h23", minute: "2-digit", second: "2-digit" };
  const formatter = new Intl.DateTimeFormat("en-GB", options);
  return formatter.format(new Date(epoch * 1000));
}

function body(event: ActivityEvent): HTMLElement {
  return event.text.length <= LONG_TEXT ? h("span", { class: "feed-text", text: event.text }) : h(
    "details",
    { class: "feed-text" },
    h("summary", { text: `${event.text.slice(0, 160)}… (${String(event.text.length)} characters)` }),
    h("span", { text: event.text }),
  );
}

export function createFeed(): Feed {
  const status = h("p", { attrs: { role: "status" }, class: "feed-state", text: STATE_TEXT.connecting });
  const list = h("ol", { attrs: { "aria-label": "Activity", role: "log" }, class: "feed" });
  const empty = h("p", { class: "empty", text: "No activity yet." });
  const scroller = h("div", { class: "feed-scroll" }, list, empty);
  const seen = new Set<number>();

  const append = (event: ActivityEvent): void => {
    if (seen.has(event.seq)) return;
    seen.add(event.seq);
    const isStick = scroller.scrollTop < 48;
    empty.hidden = true;
    list.prepend(
      h(
        "li",
        { attrs: { "data-kind": event.kind }, class: "feed-item" },
        h("span", { class: "feed-time", text: clock(event.at) }),
        h("span", { class: "feed-kind", text: event.tool === null ? event.kind : `${event.kind}: ${event.tool}` }),
        body(event),
      ),
    );
    while (list.children.length > FEED_CAP) list.lastElementChild?.remove();
    if (isStick) scroller.scrollTop = 0;
  };
  return {
    append,
    el: h("div", { class: "feed-box" }, status, scroller),
    setState: (state) => {
      status.textContent = STATE_TEXT[state];
      status.dataset.state = state;
    },
  };
}
