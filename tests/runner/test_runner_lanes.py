"""Light checks (linters) skip the build lock and queue on a light slot of their own (T2186)."""

from __future__ import annotations

import fcntl
import io
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import pytest
from runnerfakes import Env
from todoimpl.runner import buildlock, checks, lanes

if TYPE_CHECKING:
    from pathlib import Path


def _hold(name: str, seconds: float) -> None:
    """Take a lock file now, as another build would, and let it go after `seconds`."""
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    lock = (base / name).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    timer = threading.Timer(seconds, lock.close)
    timer.daemon = True
    timer.start()


@pytest.mark.parametrize(
    ("command", "lane"),
    [
        ("ruff check .", lanes.LIGHT),
        ("ruff check . && ruff format --check .", lanes.LIGHT),
        ("uv run --frozen mypy server", lanes.LIGHT),
        ("timeout 50 .venv/bin/ruff check .", lanes.LIGHT),
        ("capped.sh python3 -m mypy --strict x.py > /tmp/o 2>&1", lanes.LIGHT),
        ("FOO=1 shellcheck a.sh | head", lanes.LIGHT),
        ("git diff --check", lanes.LIGHT),
        ("make test", lanes.HEAVY),
        ("make lint", lanes.HEAVY),
        ("flutter test", lanes.HEAVY),
        ("ruff check . && flutter analyze", lanes.HEAVY),
        ("ruff check . ; pnpm build", lanes.HEAVY),
        ("uv sync", lanes.HEAVY),
        ("uv run pytest", lanes.HEAVY),
        ("python3 scripts/x.py", lanes.HEAVY),
        ("bash scripts/x.sh", lanes.HEAVY),
        ("echo hi", lanes.HEAVY),
        ("ruff check $(find . -name x)", lanes.HEAVY),
        ("ruff check `ls`", lanes.HEAVY),
        ("(ruff check .)", lanes.HEAVY),
        ("ruff check . &", lanes.HEAVY),
        ("ruff check .\nmake", lanes.HEAVY),
        ('ruff "unclosed', lanes.HEAVY),
        ("", lanes.HEAVY),
        ("pre-commit run --all-files", lanes.HEAVY),  # no config here: unknown is heavy
    ],
)
def test_t2186_a_only_a_known_linter_is_light(tmp_path: Path, command: str, lane: str) -> None:
    assert lanes.classify(command, tmp_path) == lane


def _hook(name: str, entry: str) -> str:
    return f"      - id: {name}\n        name: {name}\n        entry: {entry}\n        language: system\n"


@pytest.mark.parametrize(
    ("entry", "lane"),
    [
        ("python3 scripts/lines.py", lanes.LIGHT),
        ("scripts/none.sh", lanes.LIGHT),  # not a file: only its words count
        ("flutter analyze", lanes.HEAVY),
        ("bash scripts/app.sh", lanes.HEAVY),  # the script runs flutter
        ("python3 scripts/big.py", lanes.HEAVY),  # too big to read: unknown
        ("python3 'unclosed", lanes.HEAVY),
        ("python3 scripts/lines.py --run-tests", lanes.HEAVY),
    ],
)
def test_t2186_b_pre_commit_is_light_only_when_no_hook_builds(tmp_path: Path, entry: str, lane: str) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "lines.py").write_text("# make sure\nprint(1)\n", encoding="utf-8")
    (tmp_path / "scripts" / "app.sh").write_text("#!/bin/sh\nflutter test\n", encoding="utf-8")
    (tmp_path / "scripts" / "big.py").write_text("x = 1\n" * 20_000, encoding="utf-8")
    hooks = _hook("lines", "python3 scripts/lines.py") + _hook("other", entry)
    config = f"repos:\n  - repo: local\n    hooks:\n{hooks}"
    (tmp_path / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
    assert lanes.classify("pre-commit run --all-files", tmp_path) == lane


def test_t2186_c_a_light_check_runs_at_once_while_a_build_holds_the_lock(world: Env, tmp_path: Path) -> None:
    run_dir = tmp_path / "card9"
    _hold(buildlock.LOCK, 4.0)  # another card's flutter build
    began = time.monotonic()
    result = checks.run_check("lint", "git --version", tmp_path, run_dir, 10)
    assert result.passed
    assert time.monotonic() - began < 3.5
    assert result.lane == lanes.LIGHT
    assert result.queue_s < 1.0
    assert "waiting for build lock" not in (run_dir / result.log).read_text()


def test_t2186_d_a_light_check_queues_on_the_one_light_slot(world: Env, tmp_path: Path) -> None:
    run_dir = tmp_path / "card9"
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / lanes.LIGHT_HOLDER).write_text("card-y (ruff check .) since 2026-11-19 12:00:00\n")
    _hold(lanes.LIGHT_LOCK, 0.8)
    result = checks.run_check("lint", "git --version", tmp_path, run_dir, 10)
    assert result.passed
    assert result.queue_s >= 0.5
    log = (run_dir / result.log).read_text()
    assert log.startswith("waiting for light slot held by card-y (ruff check .) since 2026-11-19 12:00:00\n")
    assert (base / lanes.LIGHT_HOLDER).read_text() == ""


def test_t2186_e_a_build_still_waits_for_the_build_lock_not_the_light_slot(
    world: Env, tmp_path: Path
) -> None:
    _hold(lanes.LIGHT_LOCK, 4.0)  # a linter is running
    _hold(buildlock.LOCK, 0.6)
    began = time.monotonic()
    result = checks.run_check("tests", "echo build", tmp_path, tmp_path / "card9", 10)
    assert result.passed
    assert result.lane == lanes.HEAVY
    assert 0.4 <= time.monotonic() - began < 3.5


def test_t2186_f_a_held_build_lock_lets_a_light_check_through(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(buildlock.HELD_VAR, "1")
    _hold(lanes.LIGHT_LOCK, 30)
    began = time.monotonic()
    assert checks.run_capped("git --version", tmp_path, 10) == 0
    assert time.monotonic() - began < 2.0


def test_t2186_g_the_slots_say_nothing_to_a_device_and_name_no_holder_when_none_is_recorded(
    world: Env,
) -> None:
    for lock_name, slot in ((lanes.LIGHT_LOCK, lanes.light_slot), (buildlock.LOCK, None)):
        _hold(lock_name, 0.3)
        said = io.StringIO()
        gate = slot("c", "x", said) if slot else buildlock.held("c", "x", said)
        with gate:
            pass
        assert said.getvalue().startswith("waiting for ")
        assert "another" in said.getvalue()
        _hold(lock_name, 0.3)
        gate = slot("c", "x", subprocess.DEVNULL) if slot else buildlock.held("c", "x", subprocess.DEVNULL)
        with gate:
            pass


def test_t2186_h_a_script_that_cannot_be_read_is_heavy(tmp_path: Path) -> None:
    script = tmp_path / "lines.py"
    script.write_text("print(1)\n", encoding="utf-8")
    script.chmod(0)
    config = "repos:\n  - repo: local\n    hooks:\n" + _hook("lines", "python3 lines.py")
    (tmp_path / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
    assert lanes.classify("pre-commit run --all-files", tmp_path) == lanes.HEAVY
