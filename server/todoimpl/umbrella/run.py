"""The umbrella stage handler: rounds of free work, every child through its own pipeline, then settle.

Runs for the stages `implement` (the rounds) and `shipping` (kuhy's Ship click ships every child at its gate).
Children ship themselves when green (T1923). Rests at `gate` (a child whose Ship a restart cut waits),
`failed` (children need kuhy) or ends `shipped` (note closed).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, cast

from todoimpl.board import state as store
from todoimpl.runner import adopt, retry
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.pipeline import WORK_STAGES, CancelledError, LimitHitError
from todoimpl.runner.restart import INTERRUPTED, resume_ship
from todoimpl.todo_mcp.model import TodoError

from . import archived, bounce, issues, note, revive, sched
from . import store as ustore
from .children import Pool, Ticker
from .rounds import run_round
from .view import child_state, rows

if TYPE_CHECKING:
    from .driver import UmbrellaDriver

log = logging.getLogger("todoimpl.runner")
RESTING = ("paused_limit", "paused_retry")
REPO_POLL = 2.0
COUNTERS = (
    "bounces", "live_fixes", "check_fixes", "nudges", "nudge", "retries", "crash_retries", "ask_grants",
    "ask_grant_total", "ask_forms", "ask_form_total", "ship_resumes", "self_resumes", "link_nudges",
    "ship_fixes", "deploy_fixes", "reship", "gate_kills", "gate_waits", "deploy_kills", "proof_rounds",
    "gate_job",
)  # fmt: skip


class Umbrella:
    """One drive of an umbrella: its children, its record, the pool of running child drives."""

    def __init__(self, d: UmbrellaDriver) -> None:  # noqa: D107
        self.d = d
        self.run_dir = d.ctx.run_dir
        self.rec = ustore.record(d.state)
        found = note.children(d.item.body, d.state.task_id.partition("-")[0])
        self.kids = {k.cid: k for k in found if not k.dropped}
        self.dropped = [k.cid for k in found if k.dropped]  # T1924: off the umbrella, never run
        self.asked: set[str] = set()  # children whose repo was checked for archived in this drive
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
        cut = str(st.error).startswith(INTERRUPTED)  # a cut Ship goes on (T1988)
        if stopped in ("shipping", "gate"):
            st.stage = "shipping" if cut else "gate"
        elif stopped in WORK_STAGES:
            st.stage = stopped
        if st.stage in ("failed", "cancelled"):
            st.stage = "implement"
        st.error, st.last_tag, st.assignee = None, None, "claude"
        for key in COUNTERS:
            st.extra.pop(key, None)

    def resume(self, *, retry_failed: bool) -> None:
        """Restart the drive of every unfinished child; gate children ship, Retry restarts the failed ones."""
        current = self.rec.get("current")
        held = set(current["ids"]) if current else set()  # the round in progress starts them itself
        for cid, kid in self.kids.items():
            st = child_state(self.run_dir, cid)
            if st is None or kid.done or st.stage == "shipped" or cid in held:
                continue
            if (
                st.stage == "shipping"
            ):  # a restart cut its Ship: it goes on, past the cap after a wait (T2510)
                resume_ship(st, self.d.ctx.now())
            if retry_failed and (st.stage in ("failed", "cancelled") or st.last_tag in ("Q", "A")):
                self._reset(st)
                store.save(ustore.child_dir(self.run_dir, cid), st)  # a gate child is not restarted below
            if st.stage == "gate":  # they ship themselves (T1923)
                st.stage, st.auto_ship = "shipping", True
            if st.stage in (*WORK_STAGES, "shipping", *RESTING):
                store.save(ustore.child_dir(self.run_dir, cid), st)
                self.pool.start(cid, st)

    def _drop(self) -> None:
        """Stop a dropped child's turn and free its repo; the record and the rounds no longer hold it."""
        for cid in self.dropped:
            adopt.abandon(ustore.child_dir(self.run_dir, cid))
            self.d.ctx.locks.release(cid)

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
            if (
                len(batch) < width
                and not self._archived(cid)
                and locks.acquire(self.kids[cid].repo, cid) is None
            ):
                batch.append(cid)
        return batch

    def _archived(self, cid: str) -> bool:
        """Drop a child whose repo is archived (asked once a drive): box `[-]`, out of the record."""
        if cid in self.asked:
            return False
        self.asked.add(cid)
        kid = self.kids[cid]
        if not archived.archived(kid.repo):
            return False
        try:
            cast("Ticker", self.d.ctx.client).tick_child(self.d.state.task_id, kid.label, mark="-")
        except TodoError as exc:  # dropped for this drive anyway; the next drive asks again
            log.warning("dropping %s: %s", kid.repo, exc)
        self.d.activity(f"{kid.repo}: archived, dropped")
        del self.kids[cid]
        self.rec["kids"] = [k for k in self.rec["kids"] if k["id"] != cid]
        self.d.save()
        return True

    def go(self) -> str | None:
        """Run the whole umbrella drive; return the next stage."""
        d = self.d
        shipping = d.state.stage == "shipping"
        retry_failed = bool(d.state.extra.pop("retry_children", False))
        if notes := d.ctx.inbox():  # every drive empties the inbox, or the Scheduler requeues it (T2397)
            sched.forward(self.run_dir, [c for c, k in self.kids.items() if not k.done], notes)
            retry_failed = True
        self.sync()
        self._drop()
        try:
            self.resume(retry_failed=retry_failed)
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
        """Close the note when every child is done; else pause or ask kuhy."""
        d = self.d
        found, _ = rows(self.run_dir, d.state, live=False, limit_until=None)
        if not found:
            msg = "The umbrella lists no children (`## kuhyx/<repo> (<id8>)` sections)"
            raise NeedsYouError(msg, "run_failed")
        states = {r["id"]: child_state(self.run_dir, r["id"]) for r in found}
        self._pause(states)
        needy = [r for r in found if r["status"] != "done"]
        unverified = [r for r in found if r["status"] == "done" and bounce.unverified(states[r["id"]])]
        if needy and revive.children(self.run_dir, d.ctx.now()):  # board work after all: no Needs you (T2511)
            return "implement"
        if needy or unverified:  # T1953: say what each child waits for; T1955: done needs green checks
            last = {str(row.get("child")): str(row.get("symptom", "")) for row in issues.read(self.run_dir)}
            what = [(r, bounce.needs(states[r["id"]], last.get(r["repo"], ""))) for r in needy]
            what += [(r, "checks not green") for r in unverified]
            held = [(r["repo"], why) for r, why in what if bounce.undeployed(states[r["id"]])]  # T1967
            need = [(r["repo"], why) for r, why in what if not bounce.undeployed(states[r["id"]])]
            raise NeedsYouError(bounce.summary(len(found), need, held), "run_failed")
        return self._close(states)

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
