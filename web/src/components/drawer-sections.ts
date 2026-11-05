import type { TaskDetail } from "@/lib/schemas";
import type { ActionId } from "@/lib/schemas-common";

/** Drawer sections that depend only on the task detail. Buttons are supplied by the caller from actions[]. */
import { statusChip } from "@/components/card";
import { type Child, h } from "@/lib/dom";
import { formatClock, humanize } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";
import { routes } from "@/lib/routes";

export type ActionSlot = (id: ActionId) => HTMLElement | null;
const DIFF_LINE_CAP = 5000;

export function renderHead(detail: TaskDetail): HTMLElement {
  const { card } = detail;
  return h(
    "div",
    { class: "drawer-headline" },
    h("div", { class: "drawer-chips" }, statusChip(card.status), h("span", { class: "chip", text: card.repo ?? "Yours (no repo)" }), h("span", { class: "chip", text: `#${card.id}` })),
    h("h2", { attrs: { id: "drawer-title" }, class: "drawer-title", text: card.title }),
    h("p", { class: "drawer-current", text: card.current }),
  );
}

export function renderNeeds(detail: TaskDetail): HTMLElement | null {
  const { needs } = detail.card;
  if (needs === null) return detail.error === null ? null : h("p", { attrs: { role: "alert" }, class: "banner", text: detail.error });
  return h(
    "div",
    { attrs: { "data-kind": needs.kind }, class: "needs" },
    h("strong", { text: humanize(needs.kind) }),
    h("p", { text: needs.text }),
    detail.error !== null && h("p", { class: "needs-error", text: detail.error }),
  );
}

export function renderQuestions(detail: TaskDetail, act: ActionSlot): HTMLElement | null {
  if (detail.questions.length === 0) return null;
  return h(
    "section",
    { attrs: { "aria-label": "Spec questions" }, class: "block" },
    h("h3", { text: "Spec questions" }),
    h("p", { class: "hint", text: "The recommended answer is prefilled; edit it or keep it, then save." }),
    ...detail.questions.map((question) => {
      const field = h("textarea", {
        attrs: { "aria-label": `Answer to ${question.id}`, "data-keep": true, "data-qid": true, name: question.id, rows: 3 },
        text: question.answer ?? question.recommendation,
      });
      return h(
        "article",
        { class: "qcard" },
        h("h4", { text: `${question.id} · ${question.title}` }),
        question.body !== "" && h("p", { text: question.body }),
        h("p", { class: "rec" }, h("strong", { text: "Recommended: " }), question.recommendation),
        field,
        h("button", { attrs: { type: "button" }, class: "btn", on: { click: () => { field.value = question.recommendation; } }, text: "Use recommended" }),
      );
    }),
    act("spec-answers"),
    act("spec-ok"),
  );
}

export function collectAnswers(root: ParentNode): Record<string, string> {
  const answers: Record<string, string> = {};
  for (const field of root.querySelectorAll<HTMLTextAreaElement>("textarea[data-qid]")) {
    const value = field.value.trim();
    if (value !== "") answers[field.name] = value;
  }
  return answers;
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
    ...row("Note", h("span", { class: "pre", text: detail.body })),
    ...row("Done check", detail.done_check === null ? null : h("code", { text: detail.done_check })),
    ...row("Stages", stages.length > 0 ? stages.join(" → ") : null),
    ...row("Skills loaded", detail.skills_loaded.length > 0 ? detail.skills_loaded.join(", ") : null),
    ...row("Branch", detail.branch === null ? null : h("code", { text: detail.branch })),
    ...row("Worktree", detail.worktree === null ? null : h("code", { text: detail.worktree })),
    ...row("Resume", detail.resume_command === null ? null : h("code", { text: detail.resume_command })),
  );
}
