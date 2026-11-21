"""Heavy builds become tickets (T2424): a build that holds a slot for over 60 s is filed against its repo."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest
from contract_lib import validate
from runnerfakes import executable
from todoimpl.errors.sources import state_base
from todoimpl.runner import buildlock, buildqueue, heavybuild, holdceiling

BUSY = '#!/bin/bash\necho start >> "$BUILD_LOG"\nend=$((SECONDS + 20))\nwhile ((SECONDS < end)); do :; done\n'


@pytest.mark.parametrize(
    ("command", "sig"),
    [
        ("godot --headless --path /x/wt --import", "heavy-godot-import"),
        ("flutter test --coverage", "heavy-flutter-test"),
        ("uv run --frozen pytest -n 4", "heavy-uv-pytest"),
        ("pnpm --dir web run build", "heavy-pnpm-build"),
        ("pre-commit run --all-files", "heavy-pre-commit-run"),
        ("/usr/bin/cargo", "heavy-cargo"),
    ],
)
def test_t2424_a_signature_names_the_tool_and_its_step(command: str, sig: str) -> None:
    assert heavybuild.signature(command) == sig


def test_t2424_a_card_and_a_child_card_find_their_repo(tmp_path: Path) -> None:
    (tmp_path / "c1-0").mkdir()
    (tmp_path / "c1-0" / "state.json").write_text(json.dumps({"repo": "kuhyx/demo"}))
    child = tmp_path / "p2-0" / "children" / "p2-3"
    child.mkdir(parents=True)
    (child / "state.json").write_text(json.dumps({"repo": "Owner/Game_X"}))
    assert heavybuild.repo_of(tmp_path, "c1-0") == "kuhyx/demo"
    assert heavybuild.repo_of(tmp_path, "p2-3") == "Owner/Game_X"
    assert heavybuild.repo_of(tmp_path, "zz-0") is None
    assert heavybuild.repo_of(tmp_path, "?") is None


def test_t2424_the_hold_ceiling_files_a_long_held_build_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "c1-0").mkdir(parents=True)
    (home / "c1-0" / "state.json").write_text(json.dumps({"repo": "kuhyx/Demo.App"}))
    monkeypatch.setenv("TODOIMPL_HOME", str(home))
    monkeypatch.setattr(heavybuild, "LIMIT", 1.0)
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    executable(fakebin / "cargo", BUSY)
    log = tmp_path / "log"
    env = {**os.environ, "PATH": f"{shims}:{fakebin}:{os.environ['PATH']}", "BUILD_LOG": str(log)}
    argv = ["cargo", "build", "--release"]
    build = subprocess.Popen(argv, env={**env, buildlock.CARD_VAR: "c1-0"}, start_new_session=True)
    try:
        deadline = time.monotonic() + 15
        ceiling = holdceiling.Ceiling(object(), quiet=60)
        report = state_base() / "app-errors" / heavybuild.FILE
        while not report.exists():
            assert time.monotonic() < deadline, "the heavy build was never filed"
            ceiling.tick()
            time.sleep(0.1)
        for _ in range(5):
            ceiling.tick()
    finally:
        os.killpg(build.pid, signal.SIGKILL)
        build.wait(timeout=10)
    data = json.loads(report.read_text())
    validate("app-error", data, "report")
    (record,) = data["errors"]
    assert (record["app"], record["repo"]) == ("demo-app", "kuhyx/Demo.App")
    assert record["signature"] == "heavy-cargo-build"
    assert record["kind"] == "perf.heavybuild"
    assert record["count"] == 1
    assert "cargo build --release" in record["message"]
    assert "card c1-0" in record["detail"]


def test_t2424_a_second_heavy_run_counts_in_the_same_record_and_a_bad_time_is_zero() -> None:
    first = buildqueue.Ticket(7, 1, "held", "c1-0", "flutter test", "not a time")
    assert heavybuild.held_for(first, time.time()) == 0.0
    heavybuild.file(first, "kuhyx/...", 0.0)
    heavybuild.file(buildqueue.Ticket(9, 1, "held", "c2-0", "flutter test -x", "?"), "kuhyx/...", 5.0)
    (record,) = json.loads((state_base() / "app-errors" / heavybuild.FILE).read_text())["errors"]
    assert (record["app"], record["count"]) == ("repo", 2)
    assert record["detail"] == "card c2-0 held a slot 0 s: flutter test -x"


def test_t2424_a_build_of_no_known_card_is_not_filed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    ceiling = holdceiling.Ceiling(object())
    old = "2026-01-01 10:00:00"
    for seq, card in ((1, "?"), (2, "nope-0")):
        ceiling._weigh(buildqueue.Ticket(seq, 1, "held", card, "cargo build", old), tmp_path / "missing")
    assert not (state_base() / "app-errors" / heavybuild.FILE).exists()
