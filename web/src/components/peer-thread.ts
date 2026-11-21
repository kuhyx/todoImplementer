import type { TaskDetail } from "@/lib/schemas";
import type { PeerMessage } from "@/lib/schemas-peer";

/** The card's Peer thread: messages other sessions exchanged with this task. Data and icons only (textgate). */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatClock, humanize } from "@/lib/format";

const STATE_ICON: Record<PeerMessage["state"], IconName> = {
  answered: "check",
  dead_end: "failed",
  delivered: "running",
  expired: "failed",
  queued: "queued",
};

function stamp(epoch: null | number): HTMLElement | null {
  if (epoch === null) return null;
  const when = new Date(epoch * 1000);
  return h("time", { attrs: { datetime: when.toISOString() }, text: formatClock(epoch) });
}

function row(message: PeerMessage): HTMLElement {
  const state = h("span", { attrs: { "data-state-icon": "", title: humanize(message.state) }, class: "peer-state" });
  state.append(icon(STATE_ICON[message.state]));
  return h(
    "li",
    { attrs: { "data-peer": message.id, "data-state": message.state }, class: "peer-row" },
    h("div", { class: "peer-head" }, state, h("span", { attrs: { "data-from": "" }, text: message.from }), h("span", { attrs: { "aria-hidden": "true" }, text: "→" }), h("span", { attrs: { "data-to": "" }, text: message.to }), stamp(message.at), stamp(message.delivered_at), stamp(message.answered_at)),
    h("p", { attrs: { "data-text": "" }, class: "peer-text", text: message.text }),
    message.reply !== null && h("p", { attrs: { "data-reply": "" }, class: "peer-reply", text: message.reply }),
    message.reason !== null && h("p", { attrs: { "data-reason": "" }, class: "peer-reason", text: message.reason }),
  );
}

export function renderPeer(detail: TaskDetail): HTMLElement | null {
  const thread = detail.peer ?? [];
  return thread.length === 0 ? null : h("section", { attrs: { "aria-label": "Peer" }, class: "block peer" }, h("ol", { class: "peer-thread" }, ...thread.map((message) => row(message))));
}
