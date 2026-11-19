"""An umbrella round's checks queue on the build lock in view: card line and event (T2187)."""

from __future__ import annotations

import fcntl
import re
import threading
from typing import IO

from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.board.status import WAITS_FOR
from todoimpl.runner import buildlock
from umbrellarig import CARD, NOTE, at_rest, boot, manager

LINE = re.compile(r"check (?P<name>\S+): lane=(?P<lane>\w+) queue=(?P<q>[\d.]+)s run=[\d.]+s exit=(?P<e>\S+)")
LIVE = (
    {"_fake": "write", "path": "hello.txt", "text": "hi\n"},
    {"_fake": "result", "text": "- [x] C1: ran it -> saw it\n- [x] C2: ran the check -> ok\n\nD: done"},
)


def _hold() -> IO[str]:
    """Take the build lock as another card's build would; closing the file lets it go."""
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / buildlock.HOLDER).write_text("card-x (make fast) since 2026-11-19 12:00:00\n")
    lock = (base / buildlock.LOCK).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def test_t2187_a_the_round_checks_of_an_umbrella_show_their_queue_and_log_it(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1, checks={"alpha": "true"})
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIVE)
    lock = _hold()
    seen: list[object] = []
    try:
        sched.start(CARD)
        for _ in range(600):
            run = store.load(world.root / CARD)
            if run is not None and WAITS_FOR in run.extra:
                seen.append(run.extra[WAITS_FOR])
                break
            threading.Event().wait(0.05)
        threading.Event().wait(0.5)  # the check queues for a while
        lock.close()  # the other build ends
        at_rest(world, sched, "shipped")
        texts = [e["text"] for e in sched.bus.history(CARD, 0) if e["kind"] == "system"]
    finally:
        sched.close()
    assert seen
    assert seen[0]["who"] == "card-x"  # type: ignore[index]
    found = [m for t in texts if (m := LINE.match(t))]
    assert any(float(m["q"]) > 0.3 for m in found)
