"""The free-worker command: hooks off, fixed preamble, log, success judged by the worktree diff."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from todoimpl.runner import freeworker
from todoimpl.umbrella import issues

SHIM = """#!/bin/sh
printf '%s\\n' "$@" > "$ARGS_FILE"
case "$MODE" in
  edit) echo "edited" > made.txt; echo "stderr line" >&2 ;;
  grill) echo "❓ **Q1** - **Goal**: what?" ;;
  fail) echo "boom" >&2; exit 7 ;;
  noisy)
    echo "Warning: Advisor disabled - base model 'free-best' has no advisor rank" >&2
    echo '[claude-code:unrecognized_model] {"model":"free-best","query_source":"sdk"}' >&2
    echo "No changes needed." ;;
esac
exit 0
"""


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, capture_output=True)
    shim = tmp_path / "bin" / "claude-free"
    shim.parent.mkdir()
    shim.write_text(SHIM, encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}:/usr/bin:/bin")
    monkeypatch.setenv("ARGS_FILE", str(tmp_path / "args"))
    (tmp_path / "prompt.md").write_text("Do the thing in a.txt.", encoding="utf-8")
    return repo


def _run(world: Path, mode: str, monkeypatch: pytest.MonkeyPatch, *extra: str) -> int:
    monkeypatch.setenv("MODE", mode)
    tmp = world.parent
    return freeworker.main([str(world), str(tmp / "prompt.md"), str(tmp / "worker.log"), *extra])


def test_the_worker_gets_hooks_off_the_preamble_and_no_push(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(world, "edit", monkeypatch) == 0
    args = (world.parent / "args").read_text(encoding="utf-8").splitlines()
    assert args[0] == "-p"
    assert args[1].startswith(freeworker.PREAMBLE)
    assert "Do the thing in a.txt." in "\n".join(args)
    assert args[args.index("--permission-mode") + 1] == "bypassPermissions"
    assert args[args.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert "Bash(git push:*)" in args
    assert "Bash(git push *)" in args


def test_stdout_and_stderr_land_in_the_log_and_a_diff_is_success(
    world: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(world, "edit", monkeypatch) == 0
    log = (world.parent / "worker.log").read_text(encoding="utf-8")
    assert "stderr line" in log
    assert "worker exit=0" in capsys.readouterr().out


def test_a_grilling_round_without_a_diff_is_logged_and_is_no_work(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = world.parent / "run"
    code = _run(world, "grill", monkeypatch, "--issues", str(run_dir), "--child", "kuhyx/a")
    assert code == freeworker.NO_WORK
    (row,) = issues.read(run_dir)
    assert (row["child"], row["phase"], row["symptom"], row["fixed"]) == (
        "kuhyx/a",
        "start",
        freeworker.GRILLING,
        False,
    )


def test_a_failed_worker_without_a_diff_logs_its_output_tail(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = world.parent / "run"
    assert _run(world, "fail", monkeypatch, "--issues", str(run_dir)) == freeworker.NO_WORK
    (row,) = issues.read(run_dir)
    assert row["phase"] == "output"
    assert "boom" in row["symptom"]


def test_no_issue_log_requested_means_nothing_is_written(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(world, "grill", monkeypatch) == freeworker.NO_WORK
    assert not (world.parent / "run").exists()


def test_a_missing_tool_is_exit_four_and_logged(world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    run_dir = world.parent / "run"
    assert _run(world, "edit", monkeypatch, "--issues", str(run_dir)) == freeworker.NO_TOOL
    assert "not installed" in issues.read(run_dir)[0]["symptom"]


def test_a_timeout_is_logged_in_the_log_file(world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (world.parent / "bin" / "claude-free").write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    monkeypatch.setattr(freeworker, "TIMEOUT", 0.2)
    assert _run(world, "edit", monkeypatch) == freeworker.NO_WORK
    assert "timed out" in (world.parent / "worker.log").read_text(encoding="utf-8")


def test_the_command_prefix_names_this_module_and_runs_from_a_shell(tmp_path: Path) -> None:
    cmd = freeworker.command()
    assert cmd.endswith("-m todoimpl.runner.freeworker")
    done = subprocess.run(f"{cmd} --help", shell=True, capture_output=True, text=True, check=False)  # noqa: S602
    assert done.returncode == 0
    assert "prompt_file" in done.stdout


def test_the_module_runs_as_a_script(world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["freeworker", "--help"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("todoimpl.runner.freeworker", run_name="__main__")
    assert stop.value.code == 0


def test_t1884_the_issue_keeps_the_answer_and_the_model_not_the_startup_warnings(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = world.parent / "run"
    assert _run(world, "noisy", monkeypatch, "--issues", str(run_dir)) == freeworker.NO_WORK
    (row,) = issues.read(run_dir)
    assert row["symptom"] == "no edit, exit 0: No changes needed."
    assert row["model"] == "free-best"
