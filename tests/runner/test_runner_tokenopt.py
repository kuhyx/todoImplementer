"""A tokenopt run: first in the queue, unattended, ships itself, has a ~/.claude worktree, is forgotten."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from runnerfakes import FakeClient, task
from todoimpl.board.state import RunState
from todoimpl.errors import marks
from todoimpl.repotask.model import Part
from todoimpl.runner import appfix, resetwatch, tokenopt
from todoimpl.runner.resetwatch import ResetWatch
from todoimpl.runner.scheduler import Scheduler

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from runnerfakes import Env

MARK = {marks.TOKENOPT: {"key": "2027-01-15T08:00:00+00:00", "at": 1.0}}
LINE = "Reset-Key: 2027-01-15T08:00:00+00:00"


def _part(body: str) -> Part:
    return Part("aaaa1111-0", "aaaa1111", 0, "p", body, "medium", None, human=False, held=False)


def test_t2554_a_tokenopt_run_answers_to_no_one_and_ships_its_own_part_itself() -> None:
    st = RunState(task_id="x-0", stage="checks", extra=dict(MARK))
    assert marks.is_tokenopt_run(st)
    assert marks.unattended(st)
    assert marks.ships_itself(st, [_part(LINE)], "")
    assert marks.ships_itself(st, [], LINE)
    assert not marks.ships_itself(st, [_part(LINE), _part("kuhy's own")], "")
    plain = RunState(task_id="x-0", stage="checks")
    assert not marks.unattended(plain)
    assert not marks.ships_itself(plain, [_part(LINE)], LINE)


def test_t2554_the_next_cycle_forgets_the_mark() -> None:
    st = RunState(task_id="x-0", stage="shipped", extra={**MARK, "keep": 1})
    appfix.forget(st)
    assert st.extra == {"keep": 1}


def test_t2554_its_start_goes_to_the_front_of_the_queue(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root)
    seen: list[tuple[str, bool]] = []
    monkeypatch.setattr(sched, "enqueue", lambda card, *, first=False: seen.append((card, first)))
    try:
        sched.start("abcd1234-0", extra=dict(MARK))
        (world.root / "abcd1234-0" / "state.json").unlink()
        sched.start("abcd1234-0")
    finally:
        sched.close()
    assert seen == [("abcd1234-0", True), ("abcd1234-0", False)]


def _repo(path: Path) -> Path:
    for argv in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "c"]):
        subprocess.run(["git", "-C", str(path), *argv], check=True, capture_output=True)
    return path


def test_t2555_the_run_gets_a_detached_worktree_of_claude_home(tmp_path: Path) -> None:
    home = tmp_path / "claude"
    home.mkdir()
    _repo(home)
    run = tmp_path / "run" / "21b9c44a-0"
    assert tokenopt.ensure_worktree(run, home) is None
    target = run / tokenopt.WORKTREE
    head = subprocess.run(
        ["git", "-C", str(target), "branch", "--show-current"], capture_output=True, text=True, check=True
    )
    assert head.stdout.strip() == ""  # detached: a second cycle never trips over a branch
    git = ["git", "-C", str(home), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "next week"], check=True)
    assert tokenopt.ensure_worktree(run, home) is None  # kept, and moved to today's main
    assert _head(target) == _head(home)
    (target / "wip.txt").write_text("x", encoding="utf-8")
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "again"], check=True)
    why = tokenopt.ensure_worktree(run, home)
    assert why is not None
    assert "uncommitted" in why  # a dirty one stays where it is, and says so
    assert _head(target) != _head(home)
    st = RunState(task_id="x-0", stage="implement", extra=dict(MARK))
    assert tokenopt.dirs(st, run) == (target,)
    assert tokenopt.dirs(RunState(task_id="x-0", stage="implement"), run) == ()
    subprocess.run(["rm", "-rf", str(target)], check=True)
    assert tokenopt.ensure_worktree(run, home) is None  # deleted by hand: pruned and added again
    assert (target / ".git").exists()


def _head(repo: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def test_t2555_a_broken_kept_worktree_is_named(tmp_path: Path) -> None:
    target = tmp_path / "run" / tokenopt.WORKTREE
    target.mkdir(parents=True)
    (target / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
    why = tokenopt.ensure_worktree(tmp_path / "run", tmp_path)
    assert why is not None
    assert "status" in why


def test_t2555_no_claude_home_is_a_named_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "none"))
    assert tokenopt.claude_home() == tmp_path / "none"
    why = tokenopt.ensure_worktree(tmp_path / "run")
    assert why is not None
    assert "none" in why
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert tokenopt.claude_home() == tmp_path / ".claude"
    assert tokenopt.dirs(RunState(task_id="x-0", stage="implement", extra=dict(MARK)), tmp_path / "run") == ()


def test_t2555_find_skips_closed_cards_and_reads_a_plain_card() -> None:
    item = SimpleNamespace(note_id="bbbb2222")
    done = SimpleNamespace(id="a-0", status="done", parts=(), item=item, body=LINE)
    plain = SimpleNamespace(id="b-0", status="todo", parts=(), item=item, body=LINE)
    other = SimpleNamespace(id="c-0", status="todo", parts=(_part("x"),), item=item, body="")
    cards: list[Any] = [done, other, plain]
    assert tokenopt.find(cards, "2027-01-15T08:00:00+00:00") == tokenopt.Found("b-0", "bbbb2222")
    assert tokenopt.find(cards[:2], "2027-01-15T08:00:00+00:00") is None


def test_t2555_the_state_file_and_its_odd_inputs(tmp_path: Path) -> None:
    (tmp_path / resetwatch.FILE).write_text("[", encoding="utf-8")
    assert resetwatch.load(tmp_path) == {"last_reset": None, "limit_seen": None}
    data: dict[str, Any] = {"last_reset": "not a time"}
    assert resetwatch.accept(data, "2027-01-15T08:00:00+00:00")
    assert not resetwatch.accept(data, "2027-01-15T08:30:00+00:00")  # the same reset, half an hour on
    (tmp_path / "bad-0").mkdir()
    (tmp_path / "bad-0" / "state.json").write_text("{", encoding="utf-8")
    assert not resetwatch.resting(tmp_path, "bad-0")
    assert not resetwatch.started(tmp_path, "bad-0", "k")
    assert not resetwatch.started(tmp_path, "none-0", "k")
    assert resetwatch.weekly({}, None, 1.0) is None


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, card: str, event: dict[str, Any]) -> None:
        self.events.append((card, event))


def test_t2555_the_feed_line_goes_on_the_bus_and_the_thread_ticks(tmp_path: Path) -> None:
    bus = Bus()
    starter: Any = SimpleNamespace(bus=bus)
    watch = ResetWatch(tmp_path, list, starter, starter, clock=lambda: 5.0, interval=0.01)
    watch._bus_line("a-0", "token optimization after reset 2027-01-15")
    assert bus.events == [
        (
            "a-0",
            {
                "type": "activity",
                "at": 5.0,
                "kind": "system",
                "text": "token optimization after reset 2027-01-15",
                "tool": None,
            },
        )
    ]
    ResetWatch(tmp_path, list, starter, SimpleNamespace())._bus_line("a-0", "x")  # no bus: nothing
    watch.start()
    watch.start()
    watch.stop()
    assert (tmp_path / resetwatch.FILE).exists()
    ResetWatch(tmp_path, list, starter, starter).stop()  # never started


def test_t2555_a_failing_tick_is_logged_and_the_loop_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks: list[int] = []
    port: Any = SimpleNamespace()
    watch = ResetWatch(tmp_path, list, port, port, interval=0.01)

    def boom() -> None:
        ticks.append(1)
        if len(ticks) > 1:
            watch._stop.set()
        raise RuntimeError("x")

    monkeypatch.setattr(watch, "tick", boom)
    watch._loop()
    assert len(ticks) == 2
