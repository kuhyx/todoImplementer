"""A line claude writes late with an older stamp hides no newer output (T2562).

2026-11-27, card 21b9c44a-0: four shard commands of the main thread returned at +2.6, +23.8, +49.7 and
+72.6 s, then claude wrote two queued task-notification prompts stamped with the time they were queued
(-61.2 and -0.0 s). The reader took the first message line from the end, so the watch measured from the
older stamp and filed `stall-model` at 74 s though no gap was over 26 s. The fixture is that stream's
slice up to the filing tick, every text blanked; the silent copy drops the four results and still files.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from todoimpl.runner import orphans
from todoimpl.stall import report, scan
from todoimpl.stall.advisor import ADVISOR
from todoimpl.stall.watch import StallWatch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stall" / "reorder-21b9c44a.stream.jsonl"
STEM = "implement-1795775973.865"
TICK = 1795778473.5988715  # the real filing tick of stalls.jsonl
LAST = datetime.fromisoformat("2026-11-27T11:21:12.542Z").timestamp()  # shard 6's result
QUEUED = datetime.fromisoformat("2026-11-27T11:19:59.984Z").timestamp()  # the stamp the reader took


def _run(tmp_path: Path, *, silent: bool = False) -> Path:
    run_dir = tmp_path / "21b9c44a-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    shutil.copyfile(FIXTURE, stream)
    if silent:  # the same window with no tool result in it: the model truly said nothing
        rows = stream.read_text("utf-8").splitlines(keepends=True)
        stream.write_text("".join(r for r in rows if '"tool_result"' not in r or "11:19:" in r), "utf-8")
    os.utime(stream, (QUEUED, QUEUED))
    return run_dir


def _tick(tmp_path: Path) -> list[str]:
    filed: list[str] = []

    def _diagnose(_run: scan.Running) -> tuple[str, str]:
        filed.append("stall-model")
        return ("stall-model", "no command runs: waiting on the model")

    StallWatch(tmp_path, clock=lambda: TICK, diagnose=_diagnose).tick()
    return filed


def test_t2562_the_newest_stamp_wins_over_the_last_written_line(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    assert scan.last_output(run_dir, STEM) == LAST


def test_t2562_the_replayed_window_files_no_stall(tmp_path: Path) -> None:
    _run(tmp_path)
    assert _tick(tmp_path) == []
    assert not (tmp_path / report.LOG).exists()


def test_t2562_the_silent_window_still_files_one(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, silent=True)
    assert scan.last_output(run_dir, STEM) == QUEUED
    assert _tick(tmp_path) == ["stall-model"]


def test_t2562_only_the_last_written_line_carries_an_advisor_wait(tmp_path: Path) -> None:
    """An advisor call met further back was answered by the lines after it: no 240 s credit for it."""
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    content = [{"type": "server_tool_use"}]
    call = json.dumps(
        {"type": "assistant", "timestamp": "2026-11-27T11:00:00Z", "message": {"content": content}}
    )
    old = json.dumps({"type": "user", "timestamp": "2026-11-27T10:59:00Z", "message": {"content": ""}})
    (run_dir / "s.stream.jsonl").write_text(f"{call}\n{old}\n", "utf-8")
    at = datetime.fromisoformat("2026-11-27T11:00:00Z").timestamp()
    assert scan.last_output(run_dir, "s") == at
    (run_dir / "s.stream.jsonl").write_text(f"{old}\n{call}\n", "utf-8")
    assert scan.last_output(run_dir, "s") == at + ADVISOR
