"""The gate runner and its host (T1837): reuse, waiting for a unit, the systemd argv, the host's record."""

import fcntl
import json
import runpy
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from gatefakes import STAMP_TOOL, gated, steps
from runnerfakes import Env, executable, sh
from todoimpl.runner import gate, gatehost, launch, worktree
from todoimpl.runner.files import NeedsYouError


def test_t1837_a_repo_without_the_stamp_tool_has_no_gate(world: Env, tmp_path: Path) -> None:
    assert gate.run(tmp_path, tmp_path, "abcd1234-0") == []


def test_t1837_an_empty_step_list_stamps_with_write(world: Env) -> None:
    repo, wt, _ = gated(world, STAMP_TOOL.replace("printf 'one\\ntwo\\n'", "true"))
    results = gate.run(wt.path, world.root / "abcd1234-0", "abcd1234-0")
    assert [r.name for r in results] == ["gate-write"]
    assert (repo / ".git" / "worktrees" / "wt" / "gate-stamp").exists()


def test_t1837_a_finished_gate_for_the_same_tree_is_not_run_again(world: Env) -> None:
    repo, wt, _ = gated(world)
    run_dir = world.root / "abcd1234-0"
    first = gate.run(wt.path, run_dir, "abcd1234-0")
    again = gate.run(wt.path, run_dir, "abcd1234-0")
    assert [r.name for r in again] == ["gate-one", "gate-two"] == [r.name for r in first]
    assert len(steps(repo)) == 2  # two steps recorded once, not four


def test_t1837_a_failed_gate_for_the_same_tree_runs_again(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt, _ = gated(world)
    run_dir = world.root / "abcd1234-0"
    monkeypatch.setenv("FAIL_STEP", "two")
    with pytest.raises(NeedsYouError, match="gate step two is red"):
        gate.run(wt.path, run_dir, "abcd1234-0")
    monkeypatch.delenv("FAIL_STEP")
    assert [r.exit_code for r in gate.run(wt.path, run_dir, "abcd1234-0")] == [0, 0]
    assert len(steps(repo)) == 3  # `one` ran in both runs, `two` only in the second


def test_t1837_a_gate_that_never_reports_times_out(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _, wt, _ = gated(world)
    monkeypatch.setattr(gate, "_start", lambda *_a: None)
    monkeypatch.setattr(gate, "POLL", 0.01)
    monkeypatch.setattr(gate, "GATE_TIMEOUT", 0.05)
    with pytest.raises(NeedsYouError, match="did not report within"):
        gate.run(wt.path, world.root / "abcd1234-0", "abcd1234-0")


def test_t1837_a_running_unit_is_waited_for_not_started_twice(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, wt, _ = gated(world)
    run_dir = world.root / "abcd1234-0"
    starts: list[str] = []
    monkeypatch.setattr(gate, "_alive", lambda unit: unit == "todoimpl-gate-abcd1234-0")
    monkeypatch.setattr(gate, "_start", lambda *_a: starts.append("x"))
    tree = sh(wt.path, "git", "rev-parse", "HEAD^{tree}").strip()
    (run_dir / "gate").mkdir(parents=True)
    (run_dir / "gate" / "exit.json").write_text(json.dumps({"tree": "old", "steps": []}), encoding="utf-8")
    monkeypatch.setattr(gate, "POLL", 0.01)

    def finish(_s: float) -> None:  # the unit finishes while the server waits
        (run_dir / "gate" / "exit.json").write_text(
            json.dumps(
                {
                    "tree": tree,
                    "ok": True,
                    "steps": [{"name": "gate-one", "command": "c", "exit": 0, "tail": "", "log": "l"}],
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(time, "sleep", finish)
    assert [r.name for r in gate.run(wt.path, run_dir, "abcd1234-0")] == ["gate-one"]
    assert starts == []


def test_t1837_production_gate_is_its_own_systemd_unit(
    world: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(launch.LAUNCH_VAR)
    seen: list[list[str]] = []

    def fake(argv: list[str], **_kw: Any) -> Any:
        seen.append(argv)
        return type("P", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(gate, "_run", fake)
    monkeypatch.setenv("VIRTUAL_ENV", "/srv/.venv")
    gate._start("abcd1234-0", tmp_path / "run", tmp_path / "wt")
    argv = seen[0]
    assert argv[:5] == ["systemd-run", "--user", "--collect", "--quiet", "--unit=todoimpl-gate-abcd1234-0"]
    assert "RuntimeMaxSec=14400" in argv
    assert argv[argv.index("--") + 1 :] == [
        sys.executable, "-m", "todoimpl.runner.gatehost", str(tmp_path / "run"), str(tmp_path / "wt"),
    ]  # fmt: skip
    assert f"PYTHONPATH={launch.SERVER_DIR}" in argv
    assert not any(a.startswith("VIRTUAL_ENV") for a in argv)
    assert any(a.startswith("PATH=") for a in argv)
    assert gate._alive("u") is True
    seen.clear()
    monkeypatch.setattr(gate, "_run", lambda _argv, **_k: type("P", (), {"returncode": 3})())
    assert gate._alive("u") is False
    assert gate._alive(None) is False
    monkeypatch.setattr(
        gate, "_run", lambda _argv, **_k: type("P", (), {"returncode": 1, "stderr": "no bus"})()
    )
    with pytest.raises(NeedsYouError, match="could not start the gate unit todoimpl-gate-abcd1234-0: no bus"):
        gate._start("abcd1234-0", tmp_path / "run", tmp_path / "wt")


def test_t1837_the_host_writes_one_record_even_when_the_list_fails(world: Env, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    (wt / "scripts").mkdir(parents=True)
    sh(wt, "git", "init", "-q", "-b", "main")
    sh(wt, "git", "commit", "-q", "--allow-empty", "-m", "x")
    executable(wt / "scripts" / "check_gate_stamp.sh", "#!/bin/sh\necho no yaml >&2\nexit 4\n")
    assert gatehost.main([str(tmp_path / "run"), str(wt)]) == 0
    record = json.loads((tmp_path / "run" / "gate" / "exit.json").read_text(encoding="utf-8"))
    assert [(s["name"], s["exit"]) for s in record["steps"]] == [("gate-list", 4)]
    assert "no yaml" in record["steps"][0]["tail"]


def _host(world: Env, wt: worktree.Worktree) -> dict[str, Any]:
    run_dir = world.root / "abcd1234-0"
    assert gatehost.main([str(run_dir), str(wt.path)]) == 0
    sh(wt.path, "git", "status", "--short")
    return json.loads((run_dir / "gate" / "exit.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_t1837_the_host_runs_every_step_with_a_bigger_cap_and_records_the_tree(world: Env) -> None:
    _, wt, _ = gated(world)
    record = _host(world, wt)
    assert record["ok"] is True
    assert record["tree"] == sh(wt.path, "git", "rev-parse", "HEAD^{tree}").strip()
    assert [(s["name"], s["exit"]) for s in record["steps"]] == [("gate-one", 0), ("gate-two", 0)]


def test_t1837_the_host_stops_at_the_first_red_step(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _, wt, _ = gated(world)
    monkeypatch.setenv("FAIL_STEP", "one")
    record = _host(world, wt)
    assert record["ok"] is False
    assert [s["name"] for s in record["steps"]] == ["gate-one"]


def test_t1837_a_listing_that_hangs_is_recorded_not_lost(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _, wt, _ = gated(world, "#!/bin/sh\nsleep 5\n")
    monkeypatch.setattr(gatehost, "LIST_TIMEOUT", 0.2)
    record = _host(world, wt)
    assert (record["ok"], record["steps"][0]["name"], record["steps"][0]["exit"]) == (
        False,
        "gate-list",
        None,
    )
    assert "timed out" in record["steps"][0]["tail"]


def test_t1837_the_host_runs_as_a_module(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _, wt, _ = gated(world)
    run_dir = world.root / "abcd1234-0"
    monkeypatch.setattr(sys, "argv", ["gatehost", str(run_dir), str(wt.path)])
    monkeypatch.delitem(sys.modules, "todoimpl.runner.gatehost")
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.runner.gatehost", run_name="__main__", alter_sys=False)
    assert done.value.code == 0
    assert json.loads((run_dir / "gate" / "exit.json").read_text(encoding="utf-8"))["ok"] is True


def test_t1840_gates_run_one_at_a_time(world: Env) -> None:
    """Gates at once OOM-killed each other in capped.slice (tunedeck, teatr-pw): a gate waits for the lock."""
    _, wt, _ = gated(world)
    run_dir = world.root / "abcd1234-0"
    with (world.root / gatehost.LOCK_NAME).open("a", encoding="utf-8") as other:
        fcntl.flock(other, fcntl.LOCK_EX)
        late = threading.Thread(target=gatehost.main, args=([str(run_dir), str(wt.path)],))
        late.start()
        late.join(0.5)
        assert late.is_alive()
        assert not (run_dir / "gate" / "exit.json").exists()
        fcntl.flock(other, fcntl.LOCK_UN)
    late.join(20)
    assert json.loads((run_dir / "gate" / "exit.json").read_text(encoding="utf-8"))["ok"] is True


def test_t1861_gate_steps_stay_within_the_capped_sh_ceiling() -> None:
    """capped.sh refuses CAP_MEM above 4G and CAP_CPU_PCT above 20; 25 failed teatr-pw's ts-typecheck."""
    assert gatehost.STEP_ENV["CAP_MEM"] == "4G"
    assert int(gatehost.STEP_ENV["CAP_CPU_PCT"]) <= 20
