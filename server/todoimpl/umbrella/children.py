"""Running the children: a Driver thread per child, a fan-out cancel handle, the checkbox-ticking closer."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.board import state as store
from todoimpl.runner import adopt, worktree
from todoimpl.runner.launch import Handle
from todoimpl.runner.pipeline import Ctx, Driver
from todoimpl.todo_mcp.items import Item

from .store import children_root

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.model import Task

    from .note import Child

log = logging.getLogger("todoimpl.runner")


class Ticker(Protocol):
    """The parent client as a child needs it: tick a checkbox, add a follow-up note."""

    def tick_child(self, card: str, cid: str) -> None: ...  # noqa: D102
    def add_task(self, repo: str, title: str, body: str = "") -> Task: ...  # noqa: D102


class ChildClient:
    """Closes a child by ticking its checkbox in the umbrella note; follow-ups go to the real client."""

    def __init__(self, parent: Ticker, card: str, labels: dict[str, str]) -> None:  # noqa: D107
        self.parent, self.card, self.labels = parent, card, labels  # labels: run id -> checkbox label

    def close_task(self, card: str, evidence: str) -> None:  # noqa: ARG002 - the evidence is in the child's state
        """Tick the checkbox of child `card` (its run id)."""
        self.parent.tick_child(self.card, self.labels[card])

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        """Add a follow-up note the normal way."""
        return self.parent.add_task(repo, title, body)


class _FanDetach(threading.Event):
    """An event that, once set, sets the detach event of every handle in the fan (and of later ones)."""

    def __init__(self, slots: dict[str, Handle]) -> None:
        super().__init__()
        self.slots = slots

    def set(self) -> None:
        super().set()
        for handle in list(self.slots.values()):
            handle.detach.set()


@dataclass(frozen=True)
class Fan(Handle):
    """One handle for every live turn of an umbrella (manager and children): stop and detach reach all."""

    slots: dict[str, Handle] = field(default_factory=dict, compare=False)
    halt: threading.Event = field(default_factory=threading.Event, compare=False)

    def stop(self, grace: float = 3.0) -> None:
        """Stop every registered turn; turns registered later are stopped as they arrive."""
        self.halt.set()
        for handle in list(self.slots.values()):
            handle.stop(grace)

    def slot(self, name: str) -> Callable[[Handle | None], None]:
        """Return a `register` callback that files a turn under `name` (None: it ended)."""

        def register(handle: Handle | None) -> None:
            if handle is None:
                self.slots.pop(name, None)
                return
            self.slots[name] = handle
            if self.detach.is_set():
                handle.detach.set()
            if self.halt.is_set():
                threading.Thread(target=handle.stop, daemon=True).start()

        return register


def make_fan(run_dir: Path) -> Fan:
    """Return an empty fan for an umbrella run dir."""
    slots: dict[str, Handle] = {}
    return Fan(run_dir, "fan", None, _FanDetach(slots), slots)


def child_item(kid: Child) -> Item:
    """Return the child as the pipeline's item: its source note id and the original section text."""
    note, _, index = kid.cid.rpartition("-")  # ship closes `<note>-<index>` = the run id
    return Item(note, int(index), kid.title, kid.text, kid.repo, "todo", kid.done_check, "claude")


class ChildDriver(Driver):
    """A Driver whose worktree lives in the umbrella's children dir."""

    kids_root: Path = Path()

    def _worktree(self) -> None:
        worktree.attach(self.state, self.item.repo, self.kids_root)
        self.save()


class Pool:
    """The running child drives of one umbrella drive; `wait` returns when none is left."""

    def __init__(  # noqa: PLR0913, PLR0917 - what a child's Ctx is made from
        self,
        ctx: Ctx,
        fan: Fan,
        parent: Ticker,
        card: str,
        kids: dict[str, Child],
        announce: Callable[[str], None],
    ) -> None:
        """`announce(cid)` is called when a child changes stage."""
        self.ctx, self.fan, self.kids, self.announce = ctx, fan, kids, announce
        self.client = ChildClient(parent, card, {cid: kid.label for cid, kid in kids.items()})
        self.threads: dict[str, threading.Thread] = {}
        self.detached = False

    def _ctx(self, cid: str) -> Ctx:
        repo = self.kids[cid].repo

        def publish(event: dict[str, Any]) -> None:
            kind = event.get("type")
            if kind == "activity":
                self.ctx.publish({**event, "text": f"{repo}: {event['text']}"})
            elif kind == "stage":
                self.ctx.publish({"type": "activity", "at": self.ctx.now(), "kind": "system",
                                  "text": f"{repo}: {event['stage']}", "tool": None})  # fmt: skip
                self.announce(cid)

        run_dir = self.ctx.run_dir / "children" / cid
        return Ctx(
            self.ctx.root, run_dir, self.client, publish, self.fan.slot(cid), self.ctx.now,
            self.ctx.cancelled, self.ctx.check_timeout, list,
        )  # fmt: skip

    def start(self, cid: str, st: RunState) -> None:
        """Drive child `cid` (state `st`, already saved) in its own thread."""
        driver = ChildDriver(self._ctx(cid), st, child_item(self.kids[cid]))
        driver.kids_root = children_root(self.ctx.run_dir)
        thread = threading.Thread(target=self._drive, args=(driver,), name=f"child-{cid}", daemon=True)
        self.threads[cid] = thread
        thread.start()

    def _drive(self, driver: ChildDriver) -> None:
        try:
            driver.run()
        except adopt.Detached:
            self.detached = True  # the server is closing: the turn keeps running, the next server adopts it
        except Exception:
            log.exception("child %s crashed", driver.state.task_id)

    def wait(self) -> None:
        """Block until every child thread has ended."""
        for thread in list(self.threads.values()):
            thread.join()
        self.threads.clear()


def fresh_state(kid: Child, round_n: int, now: float, *, auto_ship: bool) -> store.RunState:
    """Return the run state of a child entering its first round: implement stage, normal (Opus) tier."""
    st = store.RunState(
        task_id=kid.cid, stage="implement", repo=kid.repo, started_at=now, auto_ship=auto_ship
    )
    st.note_body = store.clip_body(kid.text)
    st.extra.update(tier="normal", umbrella_round=round_n)
    return st
