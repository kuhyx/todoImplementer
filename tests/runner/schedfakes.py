"""Scheduler test helpers: canned fake-claude turns, a booted Scheduler, polling."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from runnerfakes import Env, FakeClient, make_repo, task
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState

CARD = "abcd1234-0"
PLAN_TEXT = (
    "## Approach\n- add hello.txt\n## Acceptance criteria\nC1. I run `cat hello.txt`, I see hi\n\nD: planned"
)
PLAN = ({"_fake": "result", "text": PLAN_TEXT},)
IMPL = (
    {"_fake": "write", "path": "hello.txt", "text": "hi\n"},
    {"_fake": "result", "text": "C1: done - cat shows hi\n\nD: done"},
)
LIVE_OK = ({"_fake": "result", "text": "- [x] C1: ran `cat hello.txt` -> saw hi\n\nD: done"},)
LIVE_BAD = ({"_fake": "result", "text": "- [ ] C1: ran `cat hello.txt` -> saw nothing\n\nD: done"},)


def reply(text: str, **extra: Any) -> tuple[dict[str, Any], ...]:
    """Return a turn that only replies."""
    return ({"_fake": "result", "text": text, **extra},)


def boot(world: Env, *turns: tuple[dict[str, Any], ...], **fields: Any) -> tuple[Scheduler, FakeClient]:
    """Boot a repo, a note and a Scheduler; `turns` are queued for the note's worktree in order."""
    make_repo(world)
    client = FakeClient({"abcd1234": task(**fields)})
    for turn in turns:
        world.script("abcd1234", *turn)
    return Scheduler(client, world.root, check_timeout=20), client


def state(world: Env, card: str = CARD) -> RunState:
    """Return the run's saved state."""
    st = store.load(world.root / card)
    assert st is not None
    return st


def wait(cond: Callable[[], bool], timeout: float = 20.0) -> None:
    """Poll until cond holds."""
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.02)


def wait_stage(
    world: Env, sched: Scheduler, stage: str, card: str = CARD, *, tag: str | None = None
) -> RunState:
    """Wait until the run rests in `stage` with no live drive; `tag` also needs that last_tag.

    A started run sits in its first stage while still queued (not yet active), so a stage alone
    cannot tell "not picked up yet" from "rested": pass the `tag` the drive ends on to be sure.
    """

    def done() -> bool:
        st = store.load(world.root / card)
        at_rest = st is not None and st.stage == stage and (tag is None or st.last_tag == tag)
        return at_rest and card not in sched.running()

    wait(done)
    return state(world, card)


def lift_limit(world: Env, sched: Scheduler) -> None:
    """Lift the plan limit: drop the marker and wake the dispatcher (its idle poll is seconds)."""
    (world.root / "limit-until").unlink(missing_ok=True)
    with sched._cv:
        sched._cv.notify_all()
