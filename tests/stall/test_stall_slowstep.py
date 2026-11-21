"""Slow step routing (T2437): a stall on a repo's own gate/test step goes to that repo's app-errors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from todoimpl.errors.sources import state_base
from todoimpl.runner import orphans
from todoimpl.stall import report, scan, slowstep
from todoimpl.stall.watch import LIMIT, StallWatch

CARD = "bcf6a474-0"
T0 = 1_795_200_000.0


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "run"


def _live_turn(root: Path, card: str = CARD, stem: str = f"implement-{T0 - 600:.3f}") -> Path:
    """Return a run dir whose turn record names a live claude (this test process) started at `stem`'s time."""
    run_dir = root / card
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({"repo": "kuhyx/kartka"}))
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


def _slowstep_records() -> list[dict[str, Any]]:
    path = state_base() / "app-errors" / slowstep.FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    validate("app-error", data, "report")
    return list(data["errors"])


def _board_records() -> list[dict[str, Any]]:
    path = report.path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    validate("app-error", data, "report")
    return list(data["errors"])


def _log(root: Path) -> list[dict[str, Any]]:
    path = root / report.LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_t2437_gate_step_goes_to_card_repo(root: Path) -> None:
    run_dir = _live_turn(root)
    _activity(run_dir, T0)
    clock = Clock(T0 + LIMIT + 5)
    watch = StallWatch(
        root,
        clock=clock,
        diagnose=lambda _run: (
            "stall-job-check_gate_stamp.sh",
            "waits on: scripts/check_gate_stamp.sh step gate-test-s3 2>&1 | head -2",
        ),
    )
    watch.tick()
    # Board report has no record
    assert _board_records() == []
    # Slow-steps report has one record
    records = _slowstep_records()
    assert len(records) == 1
    record = records[0]
    assert record["app"] == "kartka"
    assert record["repo"] == "kuhyx/kartka"
    assert record["signature"] == "slow-gate-test-s3"
    assert record["kind"] == "perf.slowstep"
    assert record["count"] == 1
    assert CARD in record["detail"]
    # Log row has repo
    log_rows = _log(root)
    assert len(log_rows) == 1
    assert log_rows[0]["repo"] == "kuhyx/kartka"


def test_t2437_session_wait_stays_board_stall(root: Path) -> None:
    run_dir = _live_turn(root)
    _activity(run_dir, T0)
    clock = Clock(T0 + LIMIT + 5)
    watch = StallWatch(
        root,
        clock=clock,
        diagnose=lambda _run: (
            "stall-job-journalctl",
            "waits on: journalctl --user -f -o cat -u x 2>&1 |",
        ),
    )
    watch.tick()
    # Board report has the stall record
    records = _board_records()
    assert len(records) == 1
    assert records[0]["signature"] == "stall-job-journalctl"
    # Slow-steps report does not exist
    assert not (state_base() / "app-errors" / slowstep.FILE).exists()
    # Log row has no repo
    log_rows = _log(root)
    assert len(log_rows) == 1
    assert "repo" not in log_rows[0]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("", None),
        ("A=1", None),
        ("scripts/check_gate_stamp.sh step gate-test-s3 2>&1 | head -2", "gate-test-s3"),
        (".../gate_stamp.sh step gate-lint 2>&1", "gate-lint"),
        ("scripts/test_shard.sh s2", "test-shard-s2"),
        ("CAP_CPU_PCT=20 scripts/test_shard.sh s2", "test-shard-s2"),
        ("journalctl --user -f -o cat -u x 2>&1 |", None),
        ("make test", None),
    ],
)
def test_t2437_step_of(command: str, expected: str | None) -> None:
    assert slowstep.step_of(command) == expected


def test_t2437_second_episode_counts_up(root: Path) -> None:
    """Filing the same repo+step twice increments count and updates detail."""
    slowstep.file("kuhyx/kartka", "gate-test-s3", "first detail", T0)
    slowstep.file("kuhyx/kartka", "gate-test-s3", "second detail", T0 + 1)
    records = _slowstep_records()
    assert len(records) == 1
    assert records[0]["count"] == 2
    assert records[0]["detail"] == "second detail"


def test_t2437_repo_not_known_stays_board_stall(root: Path) -> None:
    # Card name must match CARD regex: ^[0-9a-f]{8}-\d+$
    run_dir = root / "abcdefab-0"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({}))  # no repo
    orphans.begin(run_dir, f"implement-{T0 - 600:.3f}", "implement", None)
    orphans.write(run_dir, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    _activity(run_dir, T0)
    clock = Clock(T0 + LIMIT + 5)
    watch = StallWatch(
        root,
        clock=clock,
        diagnose=lambda _run: (
            "stall-job-check_gate_stamp.sh",
            "waits on: scripts/check_gate_stamp.sh step gate-test-s3 2>&1 | head -2",
        ),
    )
    watch.tick()
    # Board report has the stall record
    records = _board_records()
    assert len(records) == 1
    assert records[0]["signature"] == "stall-job-check_gate_stamp.sh"
    # Slow-steps report does not exist
    assert not (state_base() / "app-errors" / slowstep.FILE).exists()


def test_t2437_repo_is_todoimplementer_stays_board_stall(root: Path) -> None:
    run_dir = _live_turn(root, card=CARD, stem=f"implement-{T0 - 600:.3f}")
    (run_dir / "state.json").write_text(json.dumps({"repo": report.REPO}))
    _activity(run_dir, T0)
    clock = Clock(T0 + LIMIT + 5)
    watch = StallWatch(
        root,
        clock=clock,
        diagnose=lambda _run: (
            "stall-job-check_gate_stamp.sh",
            "waits on: scripts/check_gate_stamp.sh step gate-test-s3 2>&1 | head -2",
        ),
    )
    watch.tick()
    # Board report has the stall record
    records = _board_records()
    assert len(records) == 1
    assert records[0]["signature"] == "stall-job-check_gate_stamp.sh"
    # Slow-steps report does not exist
    assert not (state_base() / "app-errors" / slowstep.FILE).exists()


def test_t2437_routed_step_is_a_stall_key() -> None:
    assert report.is_stall("kartka:slow-gate-test-s3") is True
    assert report.is_stall("kartka:crash-x") is False
    assert report.is_stall("todoimplementer:stall-model") is True
