"""The follower's watchdog: no real action for 1 min names the wait; a dead one at 5 min is killed (T2198).

kuhy's rule (2026-11-19): a running card whose last real action (a tool call or result, model output) is over
1 min old is suspicious; over 5 min it must be fixed at once. A `tool_progress` heartbeat is no action (it
comes every 30 s while any tool runs), and nothing here makes a session look alive. The clock of the last real
action sits in `<stem>.real` (a restart, a deploy, keeps it). Past `SUSPICIOUS` the follower asks
`deadwait.Judge` every `LOOK_EVERY` s and shows `{since, verdict, rule, who, min}` on the card. Past
`FIX_AFTER` with a dead verdict it stops only that job, once, logs an event, and leaves the session a note:
on the job's own output (read when the tool returns) and in the inbox (the next turn, as /send does).
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from . import buildlock, deadwait
from .files import INBOX, read_json, sibling, write_json

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SUSPICIOUS = 60.0
FIX_AFTER = 300.0
LOOK_EVERY = 5.0  # seconds between two looks at a silent turn's jobs (a few /proc reads)
SAVE_EVERY = 5.0  # seconds between two writes of the real-action clock
REAL_SUFFIX = ".real"
NOISE = frozenset({"tool_progress", "rate_limit_event"})
RULES = {
    "pgrep-self": "`pgrep -f {detail}` matched only its own command line, so it never ends. Wait on a "
    "unit by name (`systemctl --user is-active <unit>`, `timeout 50 tail --pid=<pid> -f /dev/null`), "
    "never `pgrep -f` with a "
    "pattern that is in your own command",
    "cross-card": "it waited on card {detail}, which is done or gone. Never wait on another card's process: "
    "the board sequences cards",
    "deadlock": "every process in it slept in a pipe, futex or wait with no CPU for 2 min (a deadlock; a "
    "background job inside `$(...)` keeps the pipe open). Never start a background job inside `$(...)`",
}
NOTE = "(runner) Killed your dead wait `{who}` after {min} min with no real action: {rule}. Carry on.\n"


def real(line: bytes) -> bool:
    """Say whether a stream line is a real action; a heartbeat, a rate-limit notice or a blank is none."""
    if not line.strip():
        return False
    try:
        event = json.loads(line)
    except ValueError:
        return True
    return not (isinstance(event, dict) and (event.get("type") in NOISE or event.get("heartbeat") is True))


class Watch:
    """Track a turn's last real action and judge its wait once it has been silent too long."""

    def __init__(  # noqa: PLR0913 - the turn's files, its two ways out, the seams
        self,
        run_dir: Path,
        stem: str,
        show: Callable[[dict[str, Any] | None], None],
        activity: Callable[..., None],
        *,
        clock: Callable[[], float] = time.time,
        judge: deadwait.Judge | None = None,
    ) -> None:
        """Follow the turn `stem` in `run_dir`; `show` puts the silence on the card, `activity` logs."""
        self.run_dir, self.show, self.activity, self.clock = run_dir, show, activity, clock
        self.path = sibling(run_dir, stem, REAL_SUFFIX)
        saved = read_json(self.path)
        self.saved = 0.0
        self.since = float(saved) if isinstance(saved, int | float) else self._save(clock())
        self.saved = self.since
        self.judge = judge or deadwait.Judge(run_dir, buildlock.root() / buildlock.LOCK)
        self.shown: dict[str, Any] | None = None
        self.next = 0.0
        self.killed: set[deadwait.Job | None] = set()

    def _save(self, at: float) -> float:
        write_json(self.path, at, durable=False)  # a lost clock only restarts the minute count
        self.saved = at
        return at

    def heard(self, lines: list[bytes]) -> None:
        """Take the stream's new lines: a real one moves the clock and clears what the card showed."""
        if not any(real(line) for line in lines):
            return
        self.since = self.clock()
        if self.since - self.saved >= SAVE_EVERY:
            self._save(self.since)
        if self.shown is not None:
            self.shown = None
            self.show(None)

    def quiet(self, pid: int | None) -> None:
        """Look at the silent turn's jobs at most every `LOOK_EVERY` s; stop a dead one past `FIX_AFTER`."""
        now = self.clock()
        silent = now - self.since
        if silent < SUSPICIOUS or now < self.next:
            return
        self.next = now + LOOK_EVERY
        verdicts = self.judge.look(pid)
        top = deadwait.overall(verdicts)
        found = {"since": self.since, "verdict": top.verdict, "rule": top.rule, "who": top.who}
        found["min"] = int(silent // 60)
        if found != self.shown:
            self.shown = found
            self.show(found)
        if silent >= FIX_AFTER:
            for verdict in verdicts:
                if verdict.verdict == deadwait.DEAD and verdict.job not in self.killed:
                    self._fix(verdict, int(silent // 60))

    def _fix(self, verdict: deadwait.Verdict, minutes: int) -> None:
        self.killed.add(verdict.job)
        rule = RULES[verdict.rule].format(detail=verdict.detail)
        note = NOTE.format(who=verdict.who, min=minutes, rule=rule)
        deadwait.stop(verdict, note)
        path = self.run_dir / INBOX
        write_json(path, [*(read_json(path) or []), note.strip()])
        self.activity("error", note.strip())
