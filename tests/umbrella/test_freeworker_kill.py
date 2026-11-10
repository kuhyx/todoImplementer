"""A free worker killed by a signal (OOM, SIGKILL) is logged and retried a bounded number of times."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_freeworker import world  # noqa: F401 - the fixture: a git worktree with a claude-free shim on PATH
from todoimpl.runner import freeworker
from todoimpl.umbrella import issues, workers

KILLER = """#!/bin/sh
n=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
echo $((n + 1)) > "$COUNT_FILE"
[ "$n" -lt "$KILLS" ] || { echo "edited" > made.txt; exit 0; }
echo "partial" > half.txt
kill -9 $$
"""


@pytest.fixture
def killer(world: Path, monkeypatch: pytest.MonkeyPatch) -> Path:  # noqa: F811
    shim = world.parent / "bin" / "claude-free"
    shim.write_text(KILLER, encoding="utf-8")
    monkeypatch.setenv("COUNT_FILE", str(world.parent / "count"))
    monkeypatch.setattr(freeworker, "PAUSE", 0.0)
    return world


def _go(tree: Path, monkeypatch: pytest.MonkeyPatch, kills: int) -> tuple[int, Path]:
    monkeypatch.setenv("KILLS", str(kills))
    run_dir = tree.parent / "run"
    tmp = tree.parent
    code = freeworker.main(
        [
            str(tree),
            str(tmp / "prompt.md"),
            str(tmp / "w.log"),
            "--issues",
            str(run_dir),
            "--child",
            "kuhyx/a",
        ]
    )
    return code, run_dir


def test_t1903_a_killed_worker_is_logged_retried_and_the_retry_can_succeed(
    killer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, run_dir = _go(killer, monkeypatch, kills=1)
    assert code == 0
    (row,) = issues.read(run_dir)
    assert (row["child"], row["phase"]) == ("kuhyx/a", "killed")
    assert "signal" in row["symptom"]
    assert (killer.parent / "count").read_text(encoding="utf-8").strip() == "2"


def test_t1903_a_worker_killed_on_every_attempt_exits_killed_even_with_a_partial_diff(
    killer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, run_dir = _go(killer, monkeypatch, kills=99)
    assert code == freeworker.KILLED
    assert (killer / "half.txt").exists()  # the partial work is left for the manager
    assert len(issues.read(run_dir)) == freeworker.MAX_ATTEMPTS
    assert (killer.parent / "count").read_text(encoding="utf-8").strip() == str(freeworker.MAX_ATTEMPTS)


def test_every_attempt_is_recorded_for_the_tracking_view(
    killer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, run_dir = _go(killer, monkeypatch, kills=1)
    rows = workers.read(run_dir)
    assert [(r["child"], r["attempt"], r["killed"]) for r in rows] == [
        ("kuhyx/a", 1, True),
        ("kuhyx/a", 2, False),
    ]
    assert rows[0]["start"] <= rows[0]["end"] <= rows[1]["end"]
    assert rows[1]["log"] == str(killer.parent / "w.log")
