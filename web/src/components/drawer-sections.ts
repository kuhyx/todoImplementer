import type { TaskDetail } from "@/lib/schemas";
import type { ActionId } from "@/lib/schemas-common";

/** Drawer sections that depend only on the task detail. Buttons are supplied by the caller from actions[]. */
import { autoBadge, routeChip, statusChip, tierBadges, triageBadge } from "@/components/card";
import { renderNeedsLinks } from "@/components/needs-links";
import { renderParts, waitsBadge } from "@/components/repo-parts";
import { renderUmbrella } from "@/components/umbrella";
import { type Child, h } from "@/lib/dom";
import { formatClock, humanize } from "@/lib/format";
import { linkify } from "@/lib/linkify";
import { renderMarkdown } from "@/lib/markdown";
import { routes } from "@/lib/routes";

export type ActionSlot = (id: ActionId) => HTMLElement | null;
const DIFF_LINE_CAP = 5000;

export function renderHead(detail: TaskDetail): HTMLElement {
  const { card } = detail;
  return h(
    "div",
    { class: "drawer-headline" },
    h("div", { class: "drawer-chips" }, statusChip(card.status), routeChip(card), ...tierBadges(card), ...triageBadge(card), h("span", { class: "chip", text: card.repo ?? "Yours (no repo)" }), h("span", { class: "chip", text: `#${card.id}` }), card.model !== undefined && h("span", { attrs: { "data-model": "" }, class: "chip", text: card.model })),
    h("h2", { attrs: { id: "drawer-title", title: card.title }, class: "drawer-title", text: card.title }),
    h("p", { class: "drawer-current", text: card.current }),
    card.waits_on != null && waitsBadge(card.waits_on),
    card.parts !== undefined && card.parts.length > 0 && renderParts(card.parts),
    detail.umbrella !== undefined && renderUmbrella(detail.umbrella, card.id),
    card.auto !== null && h("p", { class: "drawer-auto", text: `auto: ${card.auto}` }),
    card.auto_start !== null && h("p", { class: "drawer-auto", text: autoBadge(card) ?? "" }),
  );
}

/**
 * `isQuiet` drops the need's own box (the question cards already say it) and keeps only an error banner.
 * A spec_ok need puts the Spec OK button it asks for inside its own box (kuhy, 2026-11-20).
 */
export function renderNeeds(detail: TaskDetail, isQuiet = false, act?: ActionSlot): HTMLElement | null {
  const { needs } = detail.card;
  if (needs === null || isQuiet) return detail.error === null ? null : h("p", { attrs: { role: "alert" }, class: "banner", text: detail.error });
  return h(
    "div",
    { attrs: { "data-kind": needs.kind }, class: "needs" },
    h("strong", { text: humanize(needs.kind) }),
    h("p", { text: needs.text }),
    renderNeedsLinks(needs.links),
    needs.kind === "spec_ok" && act?.("spec-ok"),
    needs.command !== undefined && h("code", { attrs: { "data-fix-command": "" }, class: "fix-command", text: needs.command }),
    // A failed run's need text is usually its error verbatim (T1950): say it once.
    detail.error !== null && detail.error !== needs.text && h("p", { class: "needs-error", text: detail.error }),
  );
}

export function renderLesson(detail: TaskDetail, act: ActionSlot): HTMLElement | null {
  const { lesson } = detail;
  return lesson === null ? null : h(
    "section",
    { attrs: { "aria-label": "Drafted lesson" }, class: "block" },
    h("h3", { text: `Lesson for skill ${lesson.skill} (${lesson.state})` }),
    h("p", {}, h("strong", { text: "Mistake: " }), lesson.mistake),
    h("p", {}, h("strong", { text: "Rule: " }), lesson.rule),
    h("p", {}, h("strong", { text: "Evidence: " }), lesson.evidence),
    act("lesson-approve"),
  );
}

export function renderPlan(detail: TaskDetail): HTMLElement {
  return detail.plan_md === null ? h("p", { class: "empty", text: "No plan yet: it is written after the spec is settled." }) : renderMarkdown(detail.plan_md);
}

function diffLine(line: string): HTMLElement {
  let kind = "ctx";
  if (line.startsWith("@@")) kind = "hunk";
  else if (/^(diff|index|---|\+\+\+)/v.test(line)) kind = "meta";
  else if (line.startsWith("+")) kind = "add";
  else if (line.startsWith("-")) kind = "del";
  return h("span", { attrs: { "data-kind": kind }, class: "diff-line", text: line });
}

export function renderDiff(detail: TaskDetail): HTMLElement {
  const { diff } = detail;
  if (diff === null) return h("p", { class: "empty", text: "No changes yet: the worktree is created at Implement." });
  const lines = diff.patch.split("\n");
  return h(
    "div",
    { class: "diff" },
    h("ul", { class: "diff-files" }, ...diff.files.map((file) => h("li", {}, h("code", { text: file.path }), h("span", { class: "plus", text: ` +${String(file.added)}` }), h("span", { class: "minus", text: ` -${String(file.removed)}` })))),
    h("pre", { class: "diff-body" }, ...lines.slice(0, DIFF_LINE_CAP).map((line) => diffLine(line))),
    (diff.truncated || lines.length > DIFF_LINE_CAP) && h("p", { class: "hint", text: "The diff is cut off here; open the worktree for the rest." }),
  );
}

export function renderChecks(detail: TaskDetail): HTMLElement {
  const { checks } = detail;
  if (checks === null) return h("p", { class: "empty", text: "No check output yet: checks run after the live check." });
  return h(
    "div",
    { class: "checks" },
    h("p", {}, h("span", { attrs: { "data-tone": checks.passed ? "ok" : "warn" }, class: "chip", text: checks.passed ? "All passed" : "Failed" }), ` ran ${formatClock(checks.ran_at)}`),
    ...checks.results.map((result) => {
      return h(
        "section",
        { attrs: { "data-exit": result.exit }, class: "check" },
        h("p", {}, h("code", { text: result.command }), h("span", { attrs: { "data-tone": result.exit === 0 ? "ok" : "warn" }, class: "chip", text: `exit ${String(result.exit)}` })),
        h("pre", { class: "md-code", text: result.tail }),
      );
    },
    ),
  );
}

function renderSelfCheck(detail: TaskDetail): HTMLElement | null {
  return detail.self_check.length === 0 ? null : h(
    "section",
    { class: "self-check" },
    h("h4", { text: "Claude's own walk through the criteria (not proof)" }),
    h("ul", { class: "md-list" }, ...detail.self_check.map((item) => h("li", {}, h("span", { class: item.done ? "md-check done" : "md-check", text: item.done ? "done" : "not done" }), item.criterion, item.note === undefined ? null : ` (${item.note})`))),
  );
}

export function renderLiveCheck(detail: TaskDetail): HTMLElement {
  const { live_check: live } = detail;
  if (live === null) return h("div", {}, h("p", { class: "empty", text: "No live check yet: Claude runs the changed app after Implement." }), renderSelfCheck(detail));
  return h(
    "div",
    { class: "live-check" },
    renderMarkdown(live.report_md),
    live.shots.length === 0 ? h("p", { class: "hint", text: "No screenshots with this report." }) : h(
      "div",
      { class: "shots" },
      ...live.shots.map((shot) => {
        const url = routes.shot(detail.card.id, shot);
        return h("figure", { class: "shot" }, h("a", { attrs: { href: url, rel: "noopener", target: "_blank" } }, h("img", { attrs: { alt: `Live check screenshot ${shot}`, loading: "lazy", src: url } })), h("figcaption", { text: shot }));
      }),
    ),
    renderSelfCheck(detail),
  );
}

function row(term: string, value: Child): HTMLElement[] {
  return value === null || value === false ? [] : [h("dt", { text: term }), h("dd", {}, value)];
}

const stageSpan = (ended: null | number): string => (ended === null ? " (running)" : ` to ${formatClock(ended)}`);

export function renderDetails(detail: TaskDetail): HTMLElement {
  const stages = detail.stages.map((s) => `${s.stage} ${formatClock(s.started)}${stageSpan(s.ended)}`);
  return h(
    "dl",
    { class: "details" },
    ...row("Note", h("span", { class: "pre" }, ...linkify(detail.body))),
    ...row("Done check", detail.done_check === null ? null : h("code", { text: detail.done_check })),
    ...row("Stages", stages.length > 0 ? stages.join(" → ") : null),
    ...row("Skills loaded", detail.skills_loaded.length > 0 ? detail.skills_loaded.join(", ") : null),
    ...row("Branch", detail.branch === null ? null : h("code", { text: detail.branch })),
    ...row("Worktree", detail.worktree === null ? null : h("code", { text: detail.worktree })),
    ...row("Resume", detail.resume_command === null ? null : h("code", { text: detail.resume_command })),
  );
}
