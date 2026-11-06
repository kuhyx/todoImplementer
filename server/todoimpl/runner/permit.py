"""Heal permission stops: learn narrow allow rules and rerun, or hand kuhy a one-line command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import allowlist, policy
from .files import NeedsYouError
from .fixcmd import command_for, grant_command, needs_tty
from .permissions import Verdict, classify
from .stream import short_input

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState

    from .pipeline import Driver
    from .session import Situation
    from .stream import Denial, TurnResult

GRANTED = "(runner) Permission is granted now for: {rules}. Redo the blocked step and carry on."
SENSITIVE = (
    "(runner) kuhy authorized edits of protected files inside this task's worktree on 2026-11-06. "
    "If Edit/Write of a file in your worktree is refused as a sensitive file, "
    "write it with a Bash command (patch or python) instead."
)
MAX_RERUNS = 2
LEGIT_STOPS = ("D", "Q")


def with_grant(st: RunState, prompt_for: Callable[[Situation], str], role: str) -> Callable[[Situation], str]:
    """Append the one-shot 'permission granted' note, and under kuhy's policy the sensitive-file advice."""
    standing = SENSITIVE if role == "implement" and policy.load().present else None

    def prompt(situation: Situation) -> str:
        notes = [n for n in (st.extra.pop("granted_note", None), standing) if n]
        return "\n\n".join([prompt_for(situation), *notes])

    return prompt


def _learn(driver: Driver, verdicts: list[Verdict]) -> None:
    st = driver.state
    keys = {"global": "", "repo": st.repo or "", "task": st.task_id}
    for verdict in verdicts:
        for rule in allowlist.add(driver.ctx.root, verdict.scope, keys[verdict.scope], verdict.rules):
            driver.activity(f"permission auto-allowed ({verdict.scope}): {rule}")


def _hand_over(st: RunState, blocked: list[tuple[Denial, Verdict]], worktree: Path) -> NeedsYouError:
    first, verdict = blocked[0]
    command = command_for(first, verdict, worktree)
    st.extra["permission"] = {"command": command, "tty": bool(command) and needs_tty(command or "")}
    more = f" (and {len(blocked) - 1} more)" if len(blocked) > 1 else ""
    text = f"Blocked {first.tool_name} {short_input(first.tool_input)}{more}: {verdict.blocked}"
    return NeedsYouError(text, "permission")


def gate(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Learn rules and return True to rerun the turn; raise NeedsYouError when only kuhy can help."""
    st = driver.state
    st.extra.pop("permission", None)
    stopped = [d for d in res.denials if d.terminal]
    if not stopped or res.tag in LEGIT_STOPS:
        st.extra.pop("perm_reruns", None)
        return False
    worktree = Path(str(st.worktree))
    strict = not policy.load().present
    judged = [(d, classify(d, worktree, driver.ctx.run_dir, strict=strict)) for d in stopped]
    judged = [(d, v) for d, v in judged if not v.ignore]
    if not judged:
        return False
    _learn(driver, [v for _, v in judged if not v.blocked])
    blocked = [(d, v) for d, v in judged if v.blocked]
    if blocked:
        raise _hand_over(st, blocked, worktree)
    rules = tuple(rule for _, v in judged for rule in v.rules)
    guided = any(v.guide for _, v in judged)
    reruns: dict[str, int] = st.extra.setdefault("perm_reruns", {})
    if reruns.get(stage, 0) >= MAX_RERUNS:
        st.extra["permission"] = {"command": grant_command(rules) if rules else None, "tty": False}
        what = ", ".join(rules) or "a sensitive file in the worktree"
        msg = f"Still denied after {MAX_RERUNS} reruns: {what}"
        raise NeedsYouError(msg, "permission")
    reruns[stage] = reruns.get(stage, 0) + 1
    notes = ([GRANTED.format(rules=", ".join(rules))] if rules else []) + ([SENSITIVE] if guided else [])
    st.extra["granted_note"] = "\n".join(notes)
    return True
