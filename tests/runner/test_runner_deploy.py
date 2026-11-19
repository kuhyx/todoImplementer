"""The deploy step (T1966): the declared command, its own systemd unit, the record the server waits for."""

import json
import runpy
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from runnerfakes import Env, make_repo, sh
from todoimpl.runner import deploy, deployhost, deployline, gatehost, launch, worktree
from todoimpl.runner.files import NeedsYouError

CARD = "abcd1234-0"
FENCED = "```\n- deploy: `echo fenced`\n```\n## Commands\n- run: `x`\n"


def _tree(world: Env, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    make_repo(world)
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    repo = world.src / "demo"
    wt = worktree.add(repo, world.root, CARD)
    return wt.path, world.root / CARD


def _deploys(world: Env) -> int:
    path = world.tmp / "deploys"
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def test_t1966_declared_reads_the_first_bullet_outside_code_fences() -> None:
    text = FENCED + "* Deploy: `bash scripts/deploy.sh --all` (notes)\n- deploy: `second`\n"
    assert deployline.declared(text) == "bash scripts/deploy.sh --all"
    assert deployline.declared("- deploy:\n- deploy: none\n- run: `deploy:`\n") is None
    assert deployline.declared(FENCED) is None


def test_t1966_a_deploy_runs_in_the_worktree_and_reports_exit_and_tail(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    got = deploy.run(wt, run_dir, CARD, "kuhyx/demo")
    assert (got.name, got.exit_code, got.passed) == ("deploy", 0, True)
    assert got.command.startswith("echo deployed")
    assert got.tail == "shim-deploy-output"
    assert (run_dir / got.log).is_file()
    assert _deploys(world) == 1


def test_t1966_a_green_record_for_the_same_commit_is_not_deployed_again(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    deploy.run(wt, run_dir, CARD, "kuhyx/demo")
    deploy.run(wt, run_dir, CARD, "kuhyx/demo")
    assert _deploys(world) == 1
    sh(wt, "git", "commit", "-q", "--allow-empty", "-m", "next")  # a new commit is a new deploy
    deploy.run(wt, run_dir, CARD, "kuhyx/demo")
    assert _deploys(world) == 2


def test_t1966_a_red_record_is_deployed_again_and_names_the_exit(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    monkeypatch.setenv("DEPLOY_EXIT", "7")
    with pytest.raises(NeedsYouError, match=r"^pushed, not deployed: deploy failed \(exit 7\): shim") as red:
        deploy.run(wt, run_dir, CARD, "kuhyx/demo")
    assert red.value.kind == "run_failed"
    monkeypatch.setenv("DEPLOY_EXIT", "0")
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo").passed
    assert _deploys(world) == 2


def test_t1966_a_running_unit_is_waited_for_not_started_twice(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    starts: list[str] = []
    monkeypatch.setattr(deploy, "_alive", lambda unit: unit == "todoimpl-deploy-abcd1234-0")
    monkeypatch.setattr(deploy, "_start", lambda *_a: starts.append("x"))
    monkeypatch.setattr(deploy, "POLL", 0.01)
    commit = sh(wt, "git", "rev-parse", "HEAD").strip()

    def finish(_s: float) -> None:  # the unit that outlived a server restart finishes while we wait
        row = {"commit": commit, "ok": True, "exit": 0, "command": "c", "tail": "t", "log": "l"}
        (run_dir / "deploy" / "exit.json").write_text(json.dumps(row), encoding="utf-8")

    (run_dir / "deploy").mkdir(parents=True)
    monkeypatch.setattr(time, "sleep", finish)
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo").tail == "t"
    assert starts == []


def test_t1966_a_deploy_that_never_reports_ends_in_needs_you(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    monkeypatch.setattr(deploy, "_start", lambda *_a: None)
    monkeypatch.setattr(deploy, "POLL", 0.01)
    monkeypatch.setattr(deploy, "WAIT", 0.05)
    with pytest.raises(NeedsYouError, match=r"^pushed, not deployed: the deploy did not report within"):
        deploy.run(wt, run_dir, CARD, "kuhyx/demo")


def test_t1966_the_test_world_never_asks_the_real_systemd(world: Env) -> None:
    assert shutil.which("systemctl") == str(world.bin / "systemctl")
    assert deploy._alive("todoimpl-deploy-abcd1234-0") is False


def test_t1966_the_unit_outlives_the_host_so_the_host_records_its_own_timeout() -> None:
    assert deploy.UNIT_MAX > deployhost.TIMEOUT
    assert deploy.WAIT > deploy.UNIT_MAX


def test_t1966_production_deploy_is_its_own_systemd_unit(
    world: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(launch.LAUNCH_VAR)
    seen: list[list[str]] = []

    def fake(argv: list[str], **_kw: Any) -> Any:
        seen.append(argv)
        return type("P", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(deploy, "_run", fake)
    deploy._start(CARD, tmp_path / "run", tmp_path / "wt", "make ship")
    argv = seen[0]
    assert argv[:5] == ["systemd-run", "--user", "--collect", "--quiet", "--unit=todoimpl-deploy-abcd1234-0"]
    assert f"RuntimeMaxSec={deploy.UNIT_MAX:.0f}" in argv
    run_dir, wt = str(tmp_path / "run"), str(tmp_path / "wt")
    assert argv[argv.index("--") + 1 :] == [
        sys.executable, "-m", "todoimpl.runner.deployhost", run_dir, wt, "make ship",
    ]  # fmt: skip
    assert f"PYTHONPATH={launch.SERVER_DIR}" in argv
    assert deploy._alive("u") is True
    assert deploy._alive(None) is False
    monkeypatch.setattr(deploy, "_run", lambda _argv, **_k: type("P", (), {"returncode": 3})())
    assert deploy._alive("u") is False
    monkeypatch.setattr(
        deploy, "_run", lambda _a, **_k: type("P", (), {"returncode": 1, "stderr": "no bus"})()
    )
    with pytest.raises(
        NeedsYouError, match="could not start the deploy unit todoimpl-deploy-abcd1234-0: no bus"
    ):
        deploy._start(CARD, tmp_path / "run", tmp_path / "wt", "make ship")


def test_t1966_the_host_records_a_timeout_as_no_exit_code(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    monkeypatch.setattr(deployhost, "TIMEOUT", 0.3)
    assert deployhost.main([str(run_dir), str(wt), "sleep 5"]) == 0
    row = json.loads((run_dir / "deploy" / "exit.json").read_text(encoding="utf-8"))
    assert (row["ok"], row["exit"], row["command"]) == (False, None, "sleep 5")
    assert "timed out" in row["tail"]
    assert row["commit"] == sh(wt, "git", "rev-parse", "HEAD").strip()


def test_t1966_the_host_runs_as_a_module_and_waits_its_turn_behind_gates(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["deployhost", str(run_dir), str(wt), "echo hi; exit 4"])
    monkeypatch.delitem(sys.modules, "todoimpl.runner.deployhost")
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.runner.deployhost", run_name="__main__", alter_sys=False)
    assert done.value.code == 0
    row = json.loads((run_dir / "deploy" / "exit.json").read_text(encoding="utf-8"))
    assert (row["ok"], row["exit"], row["tail"]) == (False, 4, "hi")
    assert (world.root / gatehost.LOCK_NAME).exists()  # the lock the gates take


def test_t1966_a_host_that_cannot_run_the_command_still_writes_its_record(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir = _tree(world, monkeypatch)
    monkeypatch.setenv("TODOIMPL_CAPPED", str(world.tmp / "no-such-capped.sh"))
    assert deployhost.main([str(run_dir), str(wt), "true"]) == 0
    row = json.loads((run_dir / "deploy" / "exit.json").read_text(encoding="utf-8"))
    assert (row["ok"], row["exit"]) == (False, deployhost.NOT_RUN)
    assert "no-such-capped.sh" in row["tail"]
