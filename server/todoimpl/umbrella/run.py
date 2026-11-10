"""The umbrella stage handler: rounds of free work, every child through its own pipeline, then settle.

Runs for the stages `implement` (the rounds) and `shipping` (kuhy's Ship click ships every child at its gate).
Children ship themselves when green (T1923). Rests at `gate` (a child whose Ship a restart cut waits),
`failed` (children need kuhy) or ends `shipped` (note closed).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, cast

from todoimpl.board import state as store
from todoimpl.runner import adopt, retry
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.pipeline import WORK_STAGES, CancelledError, LimitHitError
from todoimpl.todo_mcp.model import TodoError

from . import note
from . import store as ustore
from .children import Pool, Ticker
from .rounds import run_round
from .view import child_state, rows

if TYPE_CHECKING:
    from .driver import UmbrellaDriver

RESTING = ("paused_limit", "paused_retry")
INTERRUPTED = "Ship was interrupted by a restart: check origin and the note before shipping again"
REPO_POLL = 2.0
COUNTERS = ("live_fixes", "check_fixes", "nudges", "nudge", "retries", "crash_retries", "ask_grants")


class Umbrella:
    """One drive of an umbrella: its children, its record, the pool of running child drives."""

    def __init__(self, d: UmbrellaDriver) -> None:  # noqa: D107
        self.d = d
        self.run_dir = d.ctx.run_dir
        self.rec = ustore.record(d.state)
        self.kids = {k.cid: k for k in note.children(d.item.body, d.state.task_id.partition("-")[0])}
        self.pool = Pool(
            d.ctx, d.fan, cast("Ticker", d.ctx.client), d.state.task_id, self.kids, self._announce
        )

    def _announce(self, _cid: str) -> None:
        """Tell the page a child changed stage: it refreshes the card's counts."""
        self.d.ctx.publish({"type": "stage", "stage": self.d.state.stage})

    def sync(self) -> None:
        """Record the children in ease order (new ones appended) with the tier and done flags."""
        known = {k["id"]: k for k in self.rec["kids"]}
        ids = [*known, *(c.cid for c in note.ordered(list(self.kids.values())) if c.cid not in known)]
        self.rec["kids"] = [
            {"id": i, "repo": self.kids[i].repo, "title": self.kids[i].title, "done": self.kids[i].done}
            for i in ids
            if i in self.kids
        ]
        self.rec["tier"] = note.tier(self.d.item.body)
        self.d.save()

    def _reset(self, st: store.RunState) -> None:
        """Retry a child that needed kuhy: back to the stage it stopped in."""
        stopped = str(st.extra.pop("failed_stage", ""))
        st.stage = (
            "gate" if stopped in ("shipping", "gate") else stopped if stopped in WORK_STAGES else st.stage
        )
        if st.stage in ("failed", "cancelled"):
            st.stage = "implement"
        st.error, st.last_tag, st.assignee = None, None, "claude"
        for key in COUNTERS:
            st.extra.pop(key, None)

    def resume(self, *, shipping: bool, retry_failed: bool) -> None:
        """Restart the drive of every unfinished child; Ship moves gate children on, Retry the failed ones."""
        current = self.rec.get("current")
        held = set(current["ids"]) if current else set()  # the round in progress starts them itself
        for cid, kid in self.kids.items():
            st = child_state(self.run_dir, cid)
            if st is None or kid.done or st.stage == "shipped" or cid in held:
                continue
            if st.stage == "shipping":  # a restart cut its Ship short: check origin before shipping again
                st.extra["failed_stage"], st.stage, st.error = "gate", "failed", INTERRUPTED
                store.save(ustore.child_dir(self.run_dir, cid), st)
                continue
            cut = st.error == INTERRUPTED  # T1905: kuhy checks origin before a cut Ship goes again
            if retry_failed and (st.stage in ("failed", "cancelled") or st.last_tag in ("Q", "A")):
                self._reset(st)
                store.save(ustore.child_dir(self.run_dir, cid), st)  # a gate child is not restarted below
            if st.stage == "gate" and (shipping or not cut):  # they ship themselves (T1923)
                st.stage, st.auto_ship = "shipping", True
            if st.stage in (*WORK_STAGES, "shipping", *RESTING):
                store.save(ustore.child_dir(self.run_dir, cid), st)
                self.pool.start(cid, st)

    def _let_go(self) -> None:
        """Free the repo locks (and wait marks) of children that never started or have ended."""
        for cid in self.kids:
            self.d.ctx.locks.release(cid)

    def pending(self) -> list[str]:
        """Return the children no round took yet, in ease order."""
        taken = ustore.taken(self.rec)
        return [k["id"] for k in self.rec["kids"] if not k["done"] and k["id"] not in taken]

    def claim(self, width: int) -> list[str]:
        """Take the next `width` children, easiest first, whose repo is free (their lock is taken here)."""
        locks = self.d.ctx.locks
        batch: list[str] = []
        for cid in self.pending():
            if len(batch) < width and locks.acquire(self.kids[cid].repo, cid) is None:
                batch.append(cid)
        return batch

    def go(self) -> str | None:
        """Run the whole umbrella drive; return the next stage."""
        d = self.d
        shipping = d.state.stage == "shipping"
        retry_failed = bool(d.state.extra.pop("retry_children", False))
        self.sync()
        try:
            self.resume(shipping=shipping, retry_failed=retry_failed)
            if self.rec.get("current"):
                run_round(self, None)
            while not shipping and self.pending() and not d.ctx.cancelled():
                if batch := self.claim(int(self.rec["width"])):
                    run_round(self, batch)
                else:  # every pending child waits on its repo's other run: look again shortly
                    threading.Event().wait(REPO_POLL)
        finally:
            self.pool.wait()  # never leave child threads behind: the next drive would start them twice
            self._let_go()
        if self.pool.detached:
            raise adopt.Detached
        if d.ctx.cancelled():  # the children stopped because kuhy cancelled: that is not "children need you"
            raise CancelledError
        return self.settle()

    def settle(self) -> str | None:
        """Close the note when every child is done; else rest at the gate, pause, or ask kuhy."""
        d = self.d
        found, _ = rows(self.run_dir, d.state, live=False, limit_until=None)
        if not found:
            msg = "The umbrella lists no children (`## kuhyx/<repo> (<id8>)` sections)"
            raise NeedsYouError(msg, "run_failed")
        states = {r["id"]: child_state(self.run_dir, r["id"]) for r in found}
        self._pause(states)
        needy = [r["repo"] for r in found if r["status"] not in ("done", "ready_to_ship")]
        if needy:
            msg = f"{len(needy)} of {len(found)} children need you: {', '.join(needy[:5])}"
            raise NeedsYouError(msg, "run_failed")
        if all(r["status"] == "done" for r in found):
            return self._close(states)
        return "gate"

    def _pause(self, states: dict[str, store.RunState | None]) -> None:
        """Pause the umbrella when a child waits on the plan limit or a retry timer."""
        limit = [s.resume_at or 0.0 for s in states.values() if s is not None and s.stage == "paused_limit"]
        if limit:
            raise LimitHitError(min(limit))
        later = [s for s in states.values() if s is not None and s.stage == retry.PAUSED]
        if later:
            first = min(later, key=lambda s: s.resume_at or 0.0)
            why = str(first.extra.get("retry_reason") or "a child retries a failed turn")
            raise retry.RetryLaterError(
                first.resume_at or 0.0, why, str(first.extra.get("retry_kind", "turn"))
            )

    def _close(self, states: dict[str, store.RunState | None]) -> str:
        d = self.d
        lines = [f"Umbrella done: {len(states)} children."]
        for cid, st in states.items():
            shipped = (st.ship or {}).get("commit") if st is not None else None
            lines.append(f"{self.kids[cid].repo}: {str(shipped)[:12] if shipped else 'closed'}")
        try:
            d.ctx.client.close_task(d.state.task_id, "\n".join(lines))
        except TodoError as exc:
            msg = f"Every child is done but closing the umbrella note failed: {exc}"
            raise NeedsYouError(msg, "run_failed") from exc
        d.state.ship = {"commit": "", "closed_at": d.ctx.now()}
        return "shipped"


def run(d: UmbrellaDriver) -> str | None:
    """Stage handler for an umbrella note's `implement` and `shipping` stages."""
    return Umbrella(d).go()
