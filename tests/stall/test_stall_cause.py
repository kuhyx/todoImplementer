"""The stall's cause names the real wait: memory first, then the build lock, a job, or the model (T2402)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from todoimpl.runner import bgwait, orphans
from todoimpl.stall import cause
from todoimpl.stall.scan import Running, card_activity, turn_over

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


def test_turn_over_missing_file(tmp_path: Path) -> None:
    """Missing stream file -> turn not over."""
    assert turn_over(tmp_path / "nope", "implement-1.0") is False


def test_turn_over_torn_line(tmp_path: Path) -> None:
    """Torn line is skipped."""
    stream = tmp_path / "implement-1.0.stream.jsonl"
    stream.write_text('{"type":"assistant"}\n{"type":', "utf-8")
    assert turn_over(tmp_path, "implement-1.0") is False


def test_turn_over_output_last(tmp_path: Path) -> None:
    """Last OUTPUT line comes after result -> turn not over."""
    stream = tmp_path / "implement-1.0.stream.jsonl"
    stream.write_text(
        '{"type":"result"}\n{"type":"assistant","timestamp":"2026-11-21T00:17:11.271Z"}\n',
        "utf-8",
    )
    assert turn_over(tmp_path, "implement-1.0") is False


def test_turn_over_result_last(tmp_path: Path) -> None:
    """Result line comes after last OUTPUT -> turn over."""
    stream = tmp_path / "implement-1.0.stream.jsonl"
    stream.write_text(
        '{"type":"assistant","timestamp":"2026-11-21T00:17:11.271Z"}\n{"type":"result"}\n',
        "utf-8",
    )
    assert turn_over(tmp_path, "implement-1.0") is True


def test_turn_over_neither(tmp_path: Path) -> None:
    """No result or OUTPUT lines -> turn not over."""
    stream = tmp_path / "implement-1.0.stream.jsonl"
    stream.write_text('{"type":"system","subtype":"init"}\n', "utf-8")
    assert turn_over(tmp_path, "implement-1.0") is False


@pytest.mark.usefixtures("cgroup")
def test_t2505_ended_turn_waits_on_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Card ba5c3ff1-0 filed stall-model while its ended turn waited on a background job (T2505)."""
    run_dir = tmp_path / "ba5c3ff1-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem="implement-1.0")
    stream = run_dir / "implement-1.0.stream.jsonl"
    line1 = (
        '{"type":"user","timestamp":"2026-11-21T00:17:09.828Z",'
        '"message":{"content":[{"type":"tool_result","tool_use_id":"t1",'
        '"content":"Command running in background with ID: b1"}]}}\n'
    )
    line2 = (
        '{"type":"assistant","timestamp":"2026-11-21T00:17:11.271Z",'
        '"message":{"content":[{"type":"text","text":"Waiting on the itch publish."}]}}\n'
    )
    line3 = '{"type":"result","subtype":"success"}\n'
    stream.write_text(line1 + line2 + line3, "utf-8")

    def _scan_test(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            bgwait,
            "scan",
            lambda *_a: {"lock": False, "who": "scratch/shs.sh", "since": 100.0},
        )
        monkeypatch.setattr(bgwait, "newest", lambda _pid: 100.0)
        monkeypatch.setattr(bgwait, "job", lambda _pid: 7)
        monkeypatch.setattr(bgwait, "script", lambda pid: "scratch/shs.sh" if pid == 7 else "")

    _scan_test(monkeypatch)
    run = Running("ba5c3ff1-0", run_dir, 200.0, 1)
    assert cause.diagnose(run)[0] == "stall-job-script"

    # Also assert the existing T2449 case (no result line after the last output) still gives stall-model
    stream.write_text(line2, "utf-8")
    run2 = Running("ba5c3ff1-0", run_dir, 200.0, 1)
    assert cause.diagnose(run2) == ("stall-model", "no command runs: waiting on the model")


def test_turn_over_non_dict_line_skipped(tmp_path: Path) -> None:
    """Non-dict JSON line (array) is skipped; result before it still means turn over."""
    stream = tmp_path / "implement-1.0.stream.jsonl"
    # Top to bottom: result line, then a JSON array as the last line
    stream.write_text('{"type":"result","subtype":"success"}\n[1, 2]\n', "utf-8")
    assert turn_over(tmp_path, "implement-1.0") is True


def test_card_activity(tmp_path: Path) -> None:
    """card_activity delegates to last_activity with BOARD_TAIL."""
    root = tmp_path / "root"
    card_dir = root / "587cf325-0"
    card_dir.mkdir(parents=True)
    events = card_dir / "events.jsonl"
    events.write_text('{"type":"activity","kind":"tool","at":123.0}\n', "utf-8")
    assert card_activity(root, "587cf325-0") == 123.0
    # Missing events file -> None
    events.unlink()
    assert card_activity(root, "587cf325-0") is None
