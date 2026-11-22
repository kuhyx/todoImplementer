"""The board's `make test` check runs a sharded suite as its steps, each on its own build ticket (T2487).

2026-11-22: `make test` was one pytest run, so one build ticket held a slot 58-79 s (`heavy-uv-env`).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from todoimpl.runner import checks, checksteps, lanes

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest
    from runnerfakes import Env

SHARDED = (
    "SHELL := /bin/bash\nBAD ?= 0\nSHARDS ?= 3\ntest:\n\techo all\n\n"
    "test-shard:\n\t@echo shard $(SHARD) $(COV_DIR); [[ $(SHARD) != $(BAD) ]]\n\n"
    "test-cov:\n\t@echo cov $(COV_DIR)\n"
)


def test_t2487_a_sharded_make_test_becomes_its_steps(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(SHARDED, encoding="utf-8")
    cov = tmp_path / "a b"
    assert checksteps.steps("make test", tmp_path, cov) == [
        *(f"make test-shard SHARD={k} COV_DIR='{cov}'" for k in (1, 2, 3)),
        f"make test-cov COV_DIR='{cov}'",
    ]


def test_t2487_other_checks_and_plain_makefiles_run_as_they_are(tmp_path: Path) -> None:
    assert checksteps.steps("make test", tmp_path, tmp_path) == ["make test"]
    (tmp_path / "Makefile").write_text("test:\n\techo\n\ntest-shard:\n\techo\n", encoding="utf-8")
    assert checksteps.steps("make test", tmp_path, tmp_path) == ["make test"]
    (tmp_path / "Makefile").write_text(SHARDED, encoding="utf-8")
    hook = "pre-commit run --all-files"
    assert checksteps.steps(hook, tmp_path, tmp_path) == [hook]


def _spy(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    admitted, reported = [], []
    real = lanes.admitted
    for var in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL"):  # this suite may itself run under `make test-shard`
        monkeypatch.delenv(var, raising=False)

    @contextlib.contextmanager
    def spy(command: str, *args: object, **kwargs: object) -> Iterator[None]:
        admitted.append(command)
        with real(command, *args, **kwargs):  # type: ignore[arg-type]
            yield

    monkeypatch.setattr(lanes, "admitted", spy)
    monkeypatch.setattr(checks, "report", lambda r: reported.append(f"{r.name} {r.exit_code}"))
    return admitted, reported


def test_t2487_each_step_takes_its_own_ticket(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Makefile").write_text(SHARDED, encoding="utf-8")
    admitted, reported = _spy(monkeypatch)
    result = checks.run_check("tests", "make test", tmp_path, tmp_path / "run", 30)
    assert result.passed, result.tail
    assert (result.name, result.command) == ("tests", "make test")
    assert [a.split(" COV_DIR")[0] for a in admitted] == [
        "make test-shard SHARD=1", "make test-shard SHARD=2", "make test-shard SHARD=3", "make test-cov"
    ]  # fmt: skip
    assert reported == ["tests 1/4 0", "tests 2/4 0", "tests 3/4 0", "tests 4/4 0", "tests 0"]
    assert result.tail.splitlines()[0].startswith("shard 1 ")
    assert len({line.split()[-1] for line in result.tail.splitlines()}) == 1  # one COV_DIR for all steps
    assert result.run_s > 0


def test_t2487_a_failed_step_ends_the_check(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Makefile").write_text(SHARDED, encoding="utf-8")
    admitted, _ = _spy(monkeypatch)
    monkeypatch.setenv("BAD", "2")
    result = checks.run_check("tests", "make test", tmp_path, tmp_path / "run", 30)
    assert not result.passed
    assert len(admitted) == 2
