/** Round history: one column per round, oldest first, a chip per child by verdict; red when the round did not count. */
import type { TrackRound } from "@/lib/schemas-track";

import { icon } from "@/components/icons";
import { VERDICT_ICON } from "@/components/umbrella";
import { h } from "@/lib/dom";
import { formatSpan, stat } from "@/track/track-kit";

function chip(child: TrackRound["children"][number]): HTMLElement {
  const detail = child.detail === "" ? "" : ` (${child.detail})`;
  const notes = [child.ok ? "" : "did not count", child.free ? "" : "not a free worker"].filter((note) => note !== "");
  const text = [`${child.repo}: ${child.verdict}${detail}`, ...notes].join(", ");
  return h(
    "li",
    { attrs: { "aria-label": text, "data-ok": String(child.ok), "data-verdict": child.verdict, role: "img", title: text }, class: "t-chip" },
    icon(VERDICT_ICON[child.verdict]),
    !child.free && h("span", { attrs: { "aria-hidden": "true" }, class: "t-nofree" }),
  );
}

function column(round: TrackRound): HTMLElement {
  const took = round.started !== null && round.ended !== null ? round.ended - round.started : null;
  return h(
    "li",
    { attrs: { "data-doubled": String(round.next > round.width), "data-n": round.n }, class: "t-round" },
    h(
      "div",
      { class: "t-round-head" },
      stat("width", `Round ${String(round.n)} width`, round.width),
      round.next > round.width && stat("escalated", "The next round is wider", round.next),
      took !== null && stat("queued", "The round took", formatSpan(took)),
    ),
    h("ul", { class: "t-chips" }, ...round.children.map((child) => chip(child))),
  );
}

export function renderRounds(rounds: TrackRound[]): HTMLElement {
  return h(
    "section",
    { attrs: { "aria-label": "Rounds" }, class: "t-rounds" },
    h("ol", { class: "t-strip" }, ...rounds.map((round) => column(round))),
  );
}
