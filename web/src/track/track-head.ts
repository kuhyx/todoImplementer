/** Header of the tracking view: the segmented progress bar, bucket badges, resting reason, ETA, round and its step. */
import type { Track } from "@/lib/schemas-track";

import { type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatSpan, restingStat, stat } from "@/track/track-kit";

type Bucket = "done" | "failed" | "queued" | "running";
const BUCKETS: readonly [Bucket, IconName, string][] = [
  ["done", "check", "Done"],
  ["running", "running", "Running"],
  ["queued", "queued", "Queued"],
  ["failed", "failed", "Failed"],
];
const STEPS = ["manager", "checks", "verdict"] as const;
const STEP_LABEL: Record<(typeof STEPS)[number], string> = {
  checks: "The server runs the checks",
  manager: "The manager and its free workers are at work",
  verdict: "The server judges the round",
};

/** One segment per child, in bucket order, so the bar reads left (done) to right (failed). */
function bar(counts: Track["counts"]): HTMLElement {
  const segments = BUCKETS.flatMap(([bucket, , label]) =>
    Array.from({ length: counts[bucket] }, () => h("i", { attrs: { "data-bucket": bucket, title: label } })),
  );
  const label = `${String(counts.done)} of ${String(counts.total)} done`;
  return h("div", { attrs: { "aria-label": label, "aria-valuemax": counts.total, "aria-valuemin": 0, "aria-valuenow": counts.done, role: "meter", title: label }, class: "t-bar" }, ...segments);
}

/** Three dots for the round in progress: the step it is at and the ones before it are lit. */
function stepper(step: (typeof STEPS)[number]): HTMLElement {
  const at = STEPS.indexOf(step);
  return h(
    "span",
    { attrs: { "aria-label": STEP_LABEL[step], role: "img", title: STEP_LABEL[step] }, class: "t-steps" },
    ...STEPS.map((name, index) => h("i", { attrs: { "data-lit": index <= at, "data-now": index === at, "data-step": name } })),
  );
}

export function renderHead(track: Track, now: number): HTMLElement {
  const { counts, round } = track;
  return h(
    "header",
    { attrs: { "aria-label": "Progress" }, class: "t-head" },
    bar(counts),
    h(
      "div",
      { class: "t-stats" },
      ...BUCKETS.filter(([bucket]) => counts[bucket] > 0).map(([bucket, name, label]) => stat(name, label, counts[bucket], { "data-bucket": bucket })),
      track.needs > 0 && stat("failed", "Needs you", track.needs, { "data-needs": "" }),
      track.resting !== null && restingStat(track.resting, now),
      stat("eta", "Estimated time left", formatSpan(track.eta.seconds), { "data-eta": "" }),
      stat("running", "Round", round?.n ?? counts.round, { "data-round": "" }),
      stat("width", "Round width", round?.width ?? counts.width),
      round !== null && stepper(round.step),
      counts.issues > 0 && stat("issue", "Free-model issues", counts.issues),
    ),
  );
}
