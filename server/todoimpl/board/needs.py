"""Why a card is in Needs you: kind, the specific ask, a category and effort (answers or clicks needed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .ask import NO_REPLY, concrete_ask

if TYPE_CHECKING:
    from .state import RunState

PHONE_TEXT = "Plug in the Pixel: the app passed on the emulator and the install is staged"


@dataclass(frozen=True)
class Needs:
    """Why a card is in Needs you (needs_kind), exactly what is needed, and how much work it is."""

    kind: str
    text: str
    category: str = "action"
    effort: int = 3
    command: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the contract object (`command` only for a permission block that has a one-liner)."""
        out: dict[str, object] = {
            "kind": self.kind,
            "text": self.text,
            "category": self.category,
            "effort": self.effort,
        }
        if self.command:
            out["command"] = self.command
        return out


def _run_failed(run: RunState) -> Needs:
    text = run.error or f"The run stopped in stage {run.stage} without an error message: open Activity"
    perm = run.extra.get("permission")
    if run.stage == "failed" and isinstance(perm, dict):
        return Needs("permission", text, "permission", 1, perm.get("command"))
    if run.extra.get("auto_heal") is True:
        return Needs("run_failed", text, "auto", 1)
    if run.extra.get("failed_stage") == "live_check":
        return Needs("run_failed", text, "criteria", 2)
    return Needs("run_failed", text, "action", 4)


def _phone_wait_text(wait: object) -> str:
    """Return the criteria Claude wants checked on the Pixel, for a reply that says nothing."""
    criteria = wait.get("criteria") if isinstance(wait, dict) else None
    names = ", ".join(str(c) for c in criteria) if isinstance(criteria, list) else ""
    return f"Plug in the Pixel: Claude is waiting to check {names or 'its criteria'} on it"


def _phone_needs(run: RunState) -> Needs | None:
    """Needs of a phone wait, or None when the run does not rest on one."""
    wait, err = run.extra.get("waiting_phone"), run.error
    if not wait or run.stage == "spec_wait":  # a spec card has no phone check to wait for (T2081)
        return None
    if isinstance(wait, dict) and wait.get("tried_attached") and run.last_tag == "A" and not err:
        # The phone was in when Claude asked this, so plugging it in is not the answer.
        text = str(wait.get("note") or "") or concrete_ask(run) or NO_REPLY
        return Needs("claude_action", text, "action", 3)
    if run.last_tag == "A" and not err:
        return Needs("phone", PHONE_TEXT, "phone", 1)
    if run.last_tag != "Q":
        return Needs("claude_action", concrete_ask(run) or err or _phone_wait_text(wait), "phone", 1)
    return None


def _red_checks(run: RunState) -> str:
    """Name the checks that are still red, with their exit codes."""
    rows = (run.checks or {}).get("results")
    red = [f"{r['command']} (exit {r['exit']})" for r in rows or [] if r.get("exit") != 0]
    return "Checks are still red after the fix attempts" + (
        f": {', '.join(red)}" if red else ": open Activity"
    )


def needs(run: RunState) -> Needs:  # noqa: PLR0911 - one return per kind
    """Return the Needs for a run whose status is NEEDS_YOU."""
    err = run.error
    if (phone := _phone_needs(run)) is not None:
        return phone
    if run.assignee == "human":
        return Needs("handed_to_you", err or concrete_ask(run) or NO_REPLY, "action", 4)
    if run.stage == "spec_wait":
        if run.open_questions():
            count = len(run.open_questions())
            first = run.open_questions()[0].title
            return Needs(
                "spec_questions", f"{count} question{'' if count == 1 else 's'}: {first}", "questions", count
            )
        if run.last_tag not in ("Q", "A") and not err:
            return Needs(
                "spec_ok", "Every question is answered: click Spec OK to start the plan", "action", 1
            )
    if (
        run.stage == "failed"
        and run.checks is not None
        and not run.checks.get("passed", True)
        and not run.extra.get("permission")
    ):
        return Needs("checks_failed", err or _red_checks(run), "action", 4)
    if run.stage != "failed" and run.last_tag == "Q":
        text = concrete_ask(run) or err or NO_REPLY
        return Needs("claude_question", text, "questions", 1)
    if run.stage != "failed" and run.last_tag == "A":
        text = concrete_ask(run) or err or NO_REPLY
        return Needs("claude_action", text, "action", 3)
    return _run_failed(run)
