"""A running card idle over 60 s is logged and filed as a top-priority ticket by itself (T2402).

kuhy's rule (2026-11-20): no running card may sit more than one minute between two real activities, and
every instance is logged and becomes a fix-it ticket on its own. Real activity is an `activity` event of
the card; a stream heartbeat or a touched file is not one, so nothing can look alive by pinging.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from todoimpl.runner import orphans
from todoimpl.stall import report, scan
from todoimpl.stall.watch import LIMIT, StallWatch

CARD = "587cf325-0"
T0 = 1_795_200_000.0


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "run"


def _live_turn(root: Path, card: str = CARD, stem: str = f"implement-{T0 - 600:.3f}") -> Path:
    """Return a run dir whose turn record names a live claude (this test process) started at `stem`'s time."""
    run_dir = root / card
    run_dir.mkdir(parents=True, exist_ok=True)
    orphans.begin(run_dir, stem, "implement", None)
    orphans.write(run_dir, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    return run_dir


def _activity(run_dir: Path, at: float, kind: str = "tool") -> None:
    with (run_dir / scan.EVENTS).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "activity", "at": at, "kind": kind, "text": "x", "tool": None}) + "\n")


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _watch(root: Path, clock: Clock) -> StallWatch:
    return StallWatch(root, clock=clock, diagnose=lambda _run: ("stall-memory", "slice memory pressure 94 %"))


def _records() -> list[dict[str, Any]]:
    data = json.loads(report.path().read_text(encoding="utf-8"))
    validate("app-error", data, "report")
    return list(data["errors"])


def _log(root: Path) -> list[dict[str, Any]]:
    path = root / report.LOG
    return (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    )


def test_t2402_a_card_idle_over_a_minute_is_logged_and_filed(root: Path) -> None:
    run_dir = _live_turn(root)
    _activity(run_dir, T0)
    clock = Clock(T0 + LIMIT - 1)
    watch = _watch(root, clock)
    watch.tick()
    assert not report.path().exists()
    assert _log(root) == []
    clock.now = T0 + LIMIT + 5
    watch.tick()
    (record,) = _records()
    assert (record["app"], record["repo"], record["kind"]) == (report.APP, report.REPO, report.KIND)
    assert record["signature"] == "stall-memory"
    assert record["count"] == 1
    assert CARD in record["detail"]
    (row,) = _log(root)
    assert (row["card"], row["since"], row["signature"]) == (CARD, T0, "stall-memory")


def test_t2402_one_episode_counts_once_and_its_end_is_logged(root: Path) -> None:
    run_dir = _live_turn(root)
    _activity(run_dir, T0)
    clock = Clock(T0 + 70)
    watch = _watch(root, clock)
    for step in range(5):
        clock.now = T0 + 70 + step * 10
        watch.tick()
    assert _records()[0]["count"] == 1
    _activity(run_dir, T0 + 200)  # real work resumed
    clock.now = T0 + 205
    watch.tick()
    assert _log(root)[-1]["ended"] == T0 + 205
    clock.now = T0 + 300  # idle again: a second episode
    watch.tick()
    assert _records()[0]["count"] == 2


def test_t2402_a_new_watch_after_a_restart_does_not_count_the_same_episode_again(root: Path) -> None:
    _activity(_live_turn(root), T0)
    _watch(root, Clock(T0 + 90)).tick()
    _watch(root, Clock(T0 + 100)).tick()
    assert _records()[0]["count"] == 1


def test_t2402_board_notes_and_heartbeats_are_not_activity(root: Path) -> None:
    run_dir = _live_turn(root)
    _activity(run_dir, T0)
    _activity(run_dir, T0 + 100, kind="system")  # the board's own line on the card
    (run_dir / "implement-x.stream.jsonl").write_text('{"type":"tool_progress","heartbeat":true}\n', "utf-8")
    _watch(root, Clock(T0 + 110)).tick()
    assert _records()[0]["count"] == 1


def test_t2402_a_fresh_turn_counts_from_its_start(root: Path) -> None:
    run_dir = _live_turn(root, stem=f"implement-{T0 + 50:.3f}")
    _activity(run_dir, T0 - 3600)  # the last cycle's activity
    _watch(root, Clock(T0 + 100)).tick()
    assert not report.path().exists()


def test_t2402_cards_with_no_live_turn_are_not_watched(root: Path) -> None:
    run_dir = root / CARD
    run_dir.mkdir(parents=True)
    _activity(run_dir, T0)
    (root / "not-a-card").mkdir()
    _watch(root, Clock(T0 + 3600)).tick()
    assert not report.path().exists()
