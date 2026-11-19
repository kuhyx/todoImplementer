"""A board check's queue time and run time are recorded apart and the queue shows on the card (T2185)."""

from __future__ import annotations

import fcntl
import json
import re
import threading
import time
from typing import IO, TYPE_CHECKING, Any

from gatefakes import gated
from runnerfakes import Env, make_repo
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait, wait_stage
from todoimpl.board.card import current_line
from todoimpl.board.state import RunState
from todoimpl.board.status import SHIP_STEP, WAITS_FOR, Status
from todoimpl.runner import buildlock, checks, deploy, gate, lanes, stepwatch, worktree

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

HOLDER = "card-x (make fast) since 2026-11-19 12:00:00\n"
LINE = re.compile(
    r"check (?P<name>\S+): lane=(?P<lane>\w+) queue=(?P<q>[\d.]+)s run=(?P<r>[\d.]+)s exit=(?P<e>\S+)"
)


def _hold() -> IO[str]:
    """Take the build lock as another card's build would; closing the file lets it go."""
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / buildlock.HOLDER).write_text(HOLDER)
    lock = (base / buildlock.LOCK).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def _hold_for(seconds: float) -> None:
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / buildlock.HOLDER).write_text(HOLDER)
    lock = (base / buildlock.LOCK).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    timer = threading.Timer(seconds, lock.close)
    timer.daemon = True
    timer.start()


class Seen:
    """A watch's two outputs: the event lines and every wait put on the card."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.shown: list[dict[str, Any] | None] = []
        self.watch = stepwatch.Watch(self.said.append, self.shown.append)


def test_t2185_a_a_queued_check_shows_its_holder_and_records_queue_and_run_apart(
    world: Env, tmp_path: Path
) -> None:
    seen = Seen()
    _hold_for(0.8)
    with stepwatch.watching(seen.watch):
        result = checks.run_check("tests", "sleep 0.3", tmp_path, tmp_path / "card9", 10)
    assert result.passed
    assert result.queue_s >= 0.5
    assert 0.2 <= result.run_s < 5.0
    first, last = seen.shown[0], seen.shown[-1]
    assert first is not None
    assert (first["lock"], first["who"]) == (True, "card-x")
    assert last is None
    assert len(seen.said) == 1
    found = LINE.match(seen.said[0])
    assert found is not None
    assert (found["name"], found["lane"], found["e"]) == ("tests", "heavy", "0")
    assert float(found["q"]) >= 0.5
    assert float(found["r"]) < 5.0
    assert seen.said[0].endswith(" behind=card-x")


def test_t2185_b_an_unqueued_check_still_records_its_times_and_shows_nothing(
    world: Env, tmp_path: Path
) -> None:
    seen = Seen()
    with stepwatch.watching(seen.watch):
        checks.run_check("lint", "git --version", tmp_path, tmp_path / "card9", 10)
        checks.run_check("tests", "sleep 5", tmp_path, tmp_path / "card9", 0.2)
    assert seen.shown == []
    first, second = (LINE.match(s) for s in seen.said)
    assert first is not None
    assert second is not None
    assert (first["lane"], first["e"]) == ("light", "0")
    assert (second["lane"], second["e"]) == ("heavy", "timeout")
    assert "behind" not in seen.said[0]


def test_t2185_c_parallel_checks_show_the_longest_wait_and_clear_at_the_last() -> None:
    seen = Seen()
    seen.watch.queued(1, {"lock": True, "who": "a", "since": 200.0})
    seen.watch.queued(2, {"lock": True, "who": "b", "since": 100.0})
    seen.watch.started(2)
    seen.watch.started(1)
    seen.watch.started(1)  # a second call for a gone check changes nothing
    shown = [s["who"] if s else None for s in seen.shown]
    assert shown == ["a", "b", "a", None]


def test_t2185_d_the_card_line_names_the_lock_a_check_or_a_ship_step_waits_on() -> None:
    since = time.mktime(time.strptime("2026-11-19 12:00:00", "%Y-%m-%d %H:%M:%S"))
    run = RunState(task_id=CARD, stage="checks")
    run.extra[WAITS_FOR] = {"lock": True, "who": "card-x", "since": since}
    assert current_line(Status.WORKING, run, None, 0.0) == "⏳🔒 card-x 12:00"
    run.stage = "shipping"
    run.extra[SHIP_STEP] = "running the checks"
    assert current_line(Status.SHIPPING, run, None, 0.0) == "shipping: running the checks ⏳🔒 card-x 12:00"
    del run.extra[WAITS_FOR]
    assert current_line(Status.SHIPPING, run, None, 0.0) == "shipping: running the checks"


def test_t2185_e_a_run_whose_check_queues_shows_the_wait_then_logs_queue_and_run_in_its_events(
    world: Env,
) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    lock = _hold()  # held until the wait shows, however long the fake turns take
    try:
        sched.start(CARD)
        wait(lambda: isinstance(state(world).extra.get(WAITS_FOR), dict), 60)
        shown = state(world).extra[WAITS_FOR]
        assert (shown["lock"], shown["who"]) == (True, "card-x")
        time.sleep(0.5)
        lock.close()
        wait_stage(world, sched, "gate")
        assert WAITS_FOR not in state(world).extra
        texts = [e["text"] for e in sched.bus.history(CARD, 0) if e["kind"] == "system"]
        found = [m for t in texts if (m := LINE.match(t)) and m["name"] == "done_check"]
        assert found
        assert float(found[0]["q"]) > 0.3
        assert found[0]["e"] == "0"
    finally:
        lock.close()
        sched.close()


def test_t2185_f_a_gate_in_its_host_reports_queue_and_run_per_step_and_relays_its_wait(
    world: Env,
) -> None:
    _, wt, _ = gated(world)
    seen = Seen()
    _hold_for(1.5)
    with stepwatch.watching(seen.watch):
        results = gate.run(wt.path, world.root / "abcd1234-0", "abcd1234-0")
    assert [r.name for r in results] == ["gate-one", "gate-two"]
    assert results[0].queue_s > 0.3
    assert results[0].holder == "card-x"
    shown = [s["who"] if s else None for s in seen.shown]
    assert shown[0] == "card-x"
    assert shown[-1] is None
    lines = [LINE.match(t) for t in seen.said]
    assert [m["name"] for m in lines if m] == ["gate-one", "gate-two"]
    assert float(next(m for m in lines if m)["q"]) > 0.3
    again = Seen()  # the same tree again: the record is reused as it was, nothing new to report
    with stepwatch.watching(again.watch):
        gate.run(wt.path, world.root / "abcd1234-0", "abcd1234-0")
    assert again.said == []


def test_t2185_g_a_deploy_in_its_host_reports_queue_and_run_and_relays_its_wait(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_repo(world)
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    wt = worktree.add(world.src / "demo", world.root, "abcd1234-0")
    seen = Seen()
    _hold_for(1.5)
    with stepwatch.watching(seen.watch):
        deploy.run(wt.path, world.root / "abcd1234-0", "abcd1234-0", "kuhyx/demo")
    shown = [s["who"] if s else None for s in seen.shown]
    assert (shown[0], shown[-1]) == ("card-x", None)
    found = [m for t in seen.said if (m := LINE.match(t))]
    assert [m["name"] for m in found] == ["deploy"]
    assert float(found[0]["q"]) > 0.3


def test_t2185_h_a_hosts_wait_file_goes_up_and_comes_off_with_its_wait(tmp_path: Path) -> None:
    path = tmp_path / "gate" / stepwatch.WAIT_FILE
    host = stepwatch.host_watch(path)
    host.say("nobody reads this")
    host.queued(1, {"lock": True, "who": "card-x", "since": 5.0})
    assert json.loads(path.read_text()) == {"lock": True, "who": "card-x", "since": 5.0}
    host.started(1)
    assert not path.exists()
    stepwatch.relay(path)  # outside a drive: nothing to show it on
    seen = Seen()
    with stepwatch.watching(seen.watch):
        path.write_text('{"who": "a"}')
        stepwatch.relay(path)
        stepwatch.relay(path)  # the same wait twice is shown once
        path.unlink()
        stepwatch.relay(path)
    assert [s["who"] if s else None for s in seen.shown] == ["a", None]


def test_t2185_i_a_light_check_queued_on_the_slot_names_the_slot_holder_not_the_builds(
    world: Env, tmp_path: Path
) -> None:
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / buildlock.HOLDER).write_text("card-build (flutter test) since 2026-11-19 12:00:00\n")
    (base / lanes.LIGHT_HOLDER).write_text("card-y (ruff check .) since 2026-11-19 12:01:00\n")
    seen = Seen()
    lock = (base / lanes.LIGHT_LOCK).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    threading.Timer(0.8, lock.close).start()
    with stepwatch.watching(seen.watch):
        checks.run_check("lint", "git --version", tmp_path, tmp_path / "card9", 10)
    assert seen.shown[0] is not None
    assert seen.shown[0]["who"] == "card-y"
    assert seen.said[0].endswith(" behind=card-y")
    (base / lanes.LIGHT_HOLDER).write_text("")  # no holder recorded
    assert lanes.light_holder() == ("?", None)
    (base / lanes.LIGHT_HOLDER).write_text("? (ruff check .) since 2026-11-19 12:01:00\n")
    assert lanes.light_holder()[0] == "ruff check ."
