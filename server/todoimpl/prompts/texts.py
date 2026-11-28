"""Stage prompt texts and `build`. Short on purpose: every line is paid for on each turn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl import night
from todoimpl.newtask import images

from . import nolimitctx, phone, standing
from .kind import HINTS, detect_kind
from .research import research
from .umbrella import manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from .context import PromptContext

OVERRIDE = "override"
SPEC_NIGHT = (
    "Now kuhy sleeps (22:55-05:55): ask him nothing, reply only `D:`; the plan takes the recommended answer "
    "to every open choice and logs it."
)
TAIL_CHARS = 3000
CARD = "❓ **Q1** - **<title>**: <body>\n➡️ <your recommended answer>"
RULES = "Rules: work only in {wt}. Run heavy commands via ~/.claude/scripts/capped.sh."
BLOCKS = (
    "Claude Code blocks some Bash and Edit calls in every permission mode: no `rm` on a bare variable or a "
    "glob after `cd` or `$(...)`: use explicit absolute paths; no zsh-only expansions like `${(f)...}`; "
    "change sensitive files such as .pre-commit-config.yaml through Bash (python, sed or git apply), "
    "not Edit or Write."
)
SELF_CHECK = (
    "Self-check: walk every acceptance criterion, run the done_check yourself, and state per "
    "criterion `Cn: done` or `Cn: not done` plus one line of evidence."
)
KUHY_PLAN = (  # runner/approval.py gates Ship on these (T2362)
    "If the item or a spec answer has kuhy judge, approve or review a deliverable (mail, message, post, "
    "design), add `Cn. (kuhy) kuhy approves <it> in the board ask, then <the outward step, e.g. it is sent>`."
)
KUHY_LIVE = (  # the implement and fix stages show deliverables too, so they carry it (T2376)
    "A `(kuhy)` criterion is kuhy's, never yours to tick. Until the runner reports his `approve`, put the "
    "deliverable in your reply (full text, gaps, whether you can send or post it yourself), end `A:` with "
    "`choice c<n>: <question> | *approve | change` in an `ask` block: id `c<n>` (C6 is `c6`) and option "
    "`approve`, the only ask the runner matches. Never ask again what kuhy already answered. On a change "
    "edit only the deliverable and ask again; on `approve` do the outward step if you have the means, then "
    "tick it."
)


def item(ctx: PromptContext) -> str:
    """Item, spec answers and kuhy's notes: the part every stage shares."""
    lines = [f"Item: {ctx.title} (repo: {ctx.repo})"]
    body, pictures = images.localize(f"{ctx.body}\n{ctx.parts}".strip(), images.root())  # dufs needs a login
    if body:
        lines.append(body)
    if files := images.copy_into(pictures, ctx.run_dir):  # the run dir's own copy outlives the dufs folder
        lines.append(
            f"Files attached to this item: open each with the Read tool: {', '.join(map(str, files))}"
        )
    lines += [f"done_check: {ctx.done_check or 'none'}", *nolimitctx.pointer(ctx.run_dir)]
    if ctx.spec_answers:
        lines += ["Spec answers:", *(f"- {q}: {a}" for q, a in ctx.spec_answers)]
    if ctx.notes:
        lines += ["kuhy's notes:", *(f"- {n}" for n in ctx.notes)]
    return "\n".join(lines)


def plan_text(ctx: PromptContext) -> str:
    """Return the plan's text for a new session, its path for a resumed one."""
    if ctx.plan_md and not ctx.resumed:  # a resumed session already holds the text
        return f"Plan ({ctx.run_dir}/plan.md):\n{ctx.plan_md}"
    return f"Plan: read {ctx.run_dir}/plan.md."


def _rules(ctx: PromptContext) -> str:
    return f"{RULES.format(wt=ctx.worktree)}\n{standing.grant(ctx)}\n{BLOCKS}\n{standing.WAITS}"


def _post(*parts: str) -> str:
    """Join parts under the `override` first line every post-spec stage needs."""
    return "\n".join([OVERRIDE, *parts])


def spec(ctx: PromptContext) -> str:
    """Grill kuhy: question cards only. This stage runs before Spec OK, so no `override`."""
    return "\n".join(
        [
            "Spec stage. Grill me on this item before any plan or code.",
            item(ctx),
            "Reply with question cards only, exactly this format, a blank line between cards:",
            CARD,
            "Ask the whole frontier at once; no question may depend on another in the same round.",
            "Facts on disk are yours to find; only decisions are mine. No prose, plan, code or edits.",
            "End with `Q:`. If nothing is open, reply only `D:`.",
            *([SPEC_NIGHT] if night.is_night() else []),
        ],
    )


def plan(ctx: PromptContext) -> str:
    """Write plan.md with numbered, live-observable acceptance criteria."""
    return _post(
        "Plan stage. Research is fine; edit nothing in the repo.",
        item(ctx),
        f"Write {ctx.run_dir}/plan.md: `## Approach` (files to touch, short), `## Acceptance criteria`.",
        "Number criteria `C1.`, `C2.` ... Each is observable behaviour in the live app: `I do X, I see Y`.",
        "Never a test or code property. Cover the done_check if there is one.",
        f"{KUHY_PLAN} {phone.PLAN_WORK}",
        standing.NIGHT.rstrip(),
        "End with `D:`.",
    )


def implement(ctx: PromptContext) -> str:
    """Build it, then self-check against the plan (live exercising is the next stage)."""
    return _post(
        "Implement stage.",
        item(ctx),
        plan_text(ctx),
        _rules(ctx),
        SELF_CHECK,
        f"{KUHY_LIVE} {phone.LIVE_WORK}",
        standing.DEPLOY,
        phone.IMPLEMENT,
        "End with `D:`.",
    )


def live_check(ctx: PromptContext) -> str:
    """Exercise each criterion in the real running thing; the checklist file is the record."""
    kind = detect_kind(ctx.worktree)
    return _post(
        f"Live check stage ({kind}). Do not change code; only verify.",
        item(ctx),
        *([f"Handoff from the implementer (you are a fresh session):\n{ctx.handoff}"] if ctx.handoff else []),
        plan_text(ctx),
        f"Start the changed thing from {ctx.worktree}; exercise every criterion for real, as a user would.",
        f"Driver: {HINTS[kind]}",
        "Tests or reading code never count. No video. Never use kuhy's display :0.",
        phone.attached(ctx) if ctx.phone is not None else phone.staging(ctx),
        f"Write {ctx.run_dir}/live_check.md, one line per criterion:",
        "- [x] C1: what I did -> what I saw   (use `- [ ]` if it failed or could not be tried, and say why)",
        "A criterion that only passes once the work is on main (merged, deployed, restarted from main): land "
        "the work yourself, then check it. One that needs the Pixel: `- [~] C7: needs phone: <why>`.",
        f"{KUHY_LIVE} {phone.LIVE_WORK}",
        standing.grant(ctx),
        "Write the whole checklist yourself in this turn; no background agent, do not end with `R:`.",
        standing.WAITS,
        ctx.failure_tail[-TAIL_CHARS:],
        f"Save screenshots to {ctx.run_dir}/shots/. Stop what you started. End with `D:`.",
    )


def live_checklist(ctx: PromptContext) -> str:
    """Redo of a live check that ended without its checklist: the checklist alone, nothing re-run."""
    return _post(
        ctx.failure_tail[-TAIL_CHARS:],
        plan_text(ctx),
        f"Write {ctx.run_dir}/live_check.md, one line per plan criterion, and reply with the same lines:",
        "- [x] C1: what I did -> what I saw   (`- [ ]` not seen working, `- [~] C7: needs phone: <why>`)",
        "Then end with `D:`.",
    )


def fix(ctx: PromptContext) -> str:
    """Repair after a failed live_check or checks run, given the output tail."""
    tail = ctx.failure_tail[-TAIL_CHARS:]
    return _post(
        "Fix stage. The last live_check or checks run failed. Output tail:",
        f"```\n{tail}\n```",
        item(ctx),
        plan_text(ctx),
        _rules(ctx),
        "Find the root cause, fix it, rerun only the failing test (the board reruns the gate).",
        SELF_CHECK,
        f"{KUHY_LIVE} {phone.LIVE_WORK}",
        "End with `D:`.",
    )


def closing(ctx: PromptContext) -> str:
    """Confirm a done_check that passed on its own; read-only, the server closes the item on kuhy's click."""
    return _post(
        "Closing stage. This item's trusted done_check started passing on its own: confirm the evidence.",
        item(ctx),
        f"Work read-only in {ctx.worktree}, the repo's main checkout: never edit, commit or push anything.",
        "Run the done_check once, read its output and say in one line what it proves for this item.",
        "The server re-runs the check after your turn and decides. End with `D:`.",
    )


def resume_after_kill(ctx: PromptContext) -> str:
    """Re-orient an interrupted session from the tree and carry on."""
    return _post(
        "Your session was killed mid-work (restart or limit). Continue the stage you were in.",
        "Run `git status` and `git diff --stat` first; do not redo finished work.",
        item(ctx),
        f"Plan: {ctx.run_dir}/plan.md.",
        _rules(ctx),
        "End with `D:`.",
    )


def fresh_after_idle(ctx: PromptContext) -> str:
    """Start a new session after idle: the handoff summary is all it remembers."""
    return _post(
        "New session; the old one is gone. Handoff summary:",
        ctx.handoff or "(none)",
        item(ctx),
        f"Plan: read {ctx.run_dir}/plan.md.",
        _rules(ctx),
        "Check `git status`, then continue where the summary stops. End with `D:`.",
    )


STAGES: dict[str, Callable[[PromptContext], str]] = {
    "spec": spec,
    "plan": plan,
    "implement": implement,
    "live_check": live_check,
    "live_checklist": live_checklist,
    "fix": fix,
    "closing": closing,
    "resume_after_kill": resume_after_kill,
    "fresh_after_idle": fresh_after_idle,
    "manager": manager,
    "research": research,
}


TIERED = frozenset(
    {"implement", "fix", "resume_after_kill", "fresh_after_idle"}
)  # the implement-role prompts


def build(stage: str, ctx: PromptContext) -> str:
    """Return the prompt for `stage`; unknown stages raise ValueError (never a silent empty prompt)."""
    fn = STAGES.get(stage)
    if fn is None:
        msg = f"unknown prompt stage {stage!r}; expected one of {sorted(STAGES)}"
        raise ValueError(msg)
    text = fn(ctx)
    return f"{text}\n{ctx.tier}" if ctx.tier and stage in TIERED else text
