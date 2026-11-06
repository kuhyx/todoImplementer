"""Why a card is in Needs you: kind, the specific ask, a category and a server-computed effort (1-5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.runner.stream import last_tag_line

if TYPE_CHECKING:
    from .state import RunState

FEW_QUESTIONS, SOME_QUESTIONS = 3, 8
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


def _question_effort(count: int) -> int:
    return 1 if count <= FEW_QUESTIONS else 2 if count <= SOME_QUESTIONS else 3


def _reply_ask(run: RunState) -> str | None:
    found = last_tag_line(str(run.extra.get("last_reply", "")))
    return found[1] if found is not None and found[0] == run.last_tag and found[1] else None


def _run_failed(run: RunState) -> Needs:
    text = run.error or "The run stopped without a message"
    perm = run.extra.get("permission")
    if run.stage == "failed" and isinstance(perm, dict):
        return Needs("permission", text, "permission", 1, perm.get("command"))
    if run.extra.get("auto_heal") is True:
        return Needs("run_failed", text, "auto", 1)
    if run.extra.get("failed_stage") == "live_check":
        return Needs("run_failed", text, "criteria", 2)
    return Needs("run_failed", text, "action", 4)


def needs(run: RunState) -> Needs:  # noqa: PLR0911 - one return per kind
    """Return the Needs for a run whose status is NEEDS_YOU."""
    err = run.error
    waiting = bool(run.extra.get("waiting_phone"))
    if waiting and run.last_tag == "A" and not err:
        return Needs("phone", PHONE_TEXT, "phone", 1)
    if waiting and run.last_tag != "Q":
        return Needs("claude_action", _reply_ask(run) or err or "Waiting for the phone", "phone", 1)
    if run.assignee == "human":
        return Needs(
            "handed_to_you", err or "Claude handed this to you without saying what it needs", "action", 4
        )
    if run.stage == "spec_wait":
        if run.open_questions():
            count = len(run.open_questions())
            return Needs(
                "spec_questions",
                f"{count} open question(s) from Claude",
                "questions",
                _question_effort(count),
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
        return Needs("checks_failed", err or "Checks are still red after the fix attempts", "action", 4)
    if run.stage != "failed" and run.last_tag == "Q":
        text = _reply_ask(run) or err or "Claude asked a question: answer it with Send to Claude"
        return Needs("claude_question", text, "questions", 2)
    if run.stage != "failed" and run.last_tag == "A":
        text = _reply_ask(run) or err or "Claude needs you to do something: see the feed"
        return Needs("claude_action", text, "action", 3)
    return _run_failed(run)
