"""The stall's cause names the real wait: memory first, then the build lock, a job, or the model (T2402)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from todoimpl.runner import bgwait
from todoimpl.stall import cause
from todoimpl.stall.scan import Running

CARD = "587cf325-0"


@pytest.fixture
def cgroup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cg"
    (root / "todoimpl.slice" / "todoimpl-587cf325_0.slice").mkdir(parents=True)
    monkeypatch.setattr(cause, "CGROUP", root)
    return root / "todoimpl.slice"


def _pressure(group: Path, full: float) -> None:
    group.joinpath("memory.pressure").write_text(
        f"some avg10={full} avg60=0 avg300=0 total=1\nfull avg10={full} avg60=0 avg300=0 total=1\n", "utf-8"
    )


def _unit(group: Path, name: str, size: str) -> None:
    (group / name).mkdir(parents=True)
    (group / name / "memory.current").write_text(size, "utf-8")


def _run(tmp_path: Path) -> Running:
    return Running(CARD, tmp_path / CARD, 0.0, 1)


def _scan(monkeypatch: pytest.MonkeyPatch, wait: dict[str, Any] | None, script: str | None = None) -> None:
    monkeypatch.setattr(bgwait, "scan", lambda *_a: wait)
    monkeypatch.setattr(bgwait, "newest", lambda _pid: None if wait is None else wait["since"])
    monkeypatch.setattr(bgwait, "job", lambda _pid: None if script is None else 7)
    monkeypatch.setattr(bgwait, "script", lambda pid: script if pid == 7 else "")


def test_t2402_memory_pressure_on_the_board_names_the_biggest_unit(cgroup: Path, tmp_path: Path) -> None:
    _pressure(cgroup, 94.4)
    _unit(cgroup, "todoimpl-a_0.slice/artgate-c5-sd35c.service", str(16 << 30))
    _unit(cgroup, "todoimpl-b_0.slice/kalisz-fix-gate.service", "602112")
    _unit(cgroup, "todoimpl-b_0.slice/run-x.scope", "garbage")
    (cgroup / "todoimpl-b_0.slice" / "stray.service").write_text("", "utf-8")  # a file, not a cgroup
    signature, detail = cause.diagnose(_run(tmp_path))
    assert signature == "stall-memory"
    assert (
        detail
        == "todoimpl.slice memory pressure full avg10=94%; biggest unit artgate-c5-sd35c.service 16.0 GiB"
    )


def test_t2402_memory_pressure_in_the_cards_own_slice_counts_too(cgroup: Path, tmp_path: Path) -> None:
    _pressure(cgroup / "todoimpl-587cf325_0.slice", 50)
    signature, detail = cause.diagnose(_run(tmp_path))
    assert signature == "stall-memory"
    assert detail == "todoimpl-587cf325_0.slice memory pressure full avg10=50%"


@pytest.mark.usefixtures("cgroup")
def test_t2402_without_pressure_the_build_lock_a_job_or_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scan(monkeypatch, {"lock": True, "who": "ba5c3ff1-0", "since": 1.0})
    assert cause.diagnose(_run(tmp_path)) == ("stall-buildlock", "waits on the build lock held by ba5c3ff1-0")
    _scan(monkeypatch, {"lock": False, "who": "/usr/bin/Systemd-Run --user --wait make", "since": 1.0})
    assert cause.diagnose(_run(tmp_path)) == (
        "stall-job-make", "waits on: /usr/bin/Systemd-Run --user --wait make",
    )  # fmt: skip
    _scan(monkeypatch, {"lock": False, "who": "", "since": 1.0})
    assert cause.diagnose(_run(tmp_path))[0] == "stall-job-shell"
    _scan(monkeypatch, None)
    assert cause.diagnose(_run(tmp_path)) == ("stall-model", "no command runs: waiting on the model")


def test_t2402_an_unreadable_pressure_file_is_no_pressure(tmp_path: Path) -> None:
    assert cause.pressure(tmp_path / "missing") == 0.0
    assert cause.biggest(tmp_path / "missing") is None


@pytest.mark.usefixtures("cgroup")
def test_t2441_the_signature_reads_the_whole_script_not_the_cards_60_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = "/home/kuhy/src/todoImplementer"
    whole = f"PYTHONPATH={home}/server {home}/.venv/bin/python -m x"
    cut = whole[:60]
    _scan(monkeypatch, {"lock": False, "who": cut, "since": 1.0}, whole)
    assert cause.diagnose(_run(tmp_path)) == ("stall-job-python", f"waits on: {cut}")


@pytest.mark.usefixtures("cgroup")
def test_t2449_a_job_older_than_the_last_activity_is_the_models_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capped call's job lives on, but its result reached the model: the quiet is the model's (T2449)."""
    _scan(monkeypatch, {"lock": False, "who": "scratch/shs.sh", "since": 100.0}, "scratch/shs.sh")
    run = Running(CARD, tmp_path / CARD, 200.0, 1)
    assert cause.diagnose(run) == ("stall-model", "no command runs: waiting on the model")
    monkeypatch.setattr(bgwait, "newest", lambda _pid: 199.5)  # a job started with the last activity
    assert cause.diagnose(run)[0] == "stall-job-script"
    monkeypatch.setattr(bgwait, "newest", lambda _pid: None)  # its start cannot be read: still a job
    assert cause.diagnose(run)[0] == "stall-job-script"
