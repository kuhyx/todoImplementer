import subprocess
from pathlib import Path

from todoimpl.runner import orphans


def _turn(cwd: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sleep", "60"], cwd=cwd, start_new_session=True)


def test_reap_kills_the_recorded_group_and_forgets_the_record(tmp_path: Path) -> None:
    turn = _turn(tmp_path)
    orphans.record(tmp_path, turn.pid)
    assert orphans.reap(tmp_path, grace=0.0) == turn.pid
    assert turn.wait(timeout=10) < 0
    assert not (tmp_path / orphans.RECORD).exists()


def test_reap_waits_out_the_grace_for_a_group_that_exits_on_sigterm(tmp_path: Path) -> None:
    turn = _turn(tmp_path)
    orphans.record(tmp_path, turn.pid)
    assert orphans.reap(tmp_path) == turn.pid  # the zombie counts as dead, so this does not wait 3 s
    turn.wait(timeout=10)


def test_reap_without_a_record_kills_nothing(tmp_path: Path) -> None:
    other = _turn(tmp_path)  # cwd inside the run, but never recorded
    try:
        assert orphans.reap(tmp_path) is None
        assert other.poll() is None
    finally:
        other.kill()


def test_a_record_of_a_reused_pid_is_ignored(tmp_path: Path) -> None:
    other = _turn(tmp_path)
    try:
        orphans.record(tmp_path, other.pid)
        (tmp_path / orphans.RECORD).write_text(f'{{"pid": {other.pid}, "start": "1"}}', encoding="utf-8")
        assert orphans.reap(tmp_path) is None
        assert other.poll() is None
    finally:
        other.kill()


def test_a_broken_record_is_ignored(tmp_path: Path) -> None:
    (tmp_path / orphans.RECORD).write_text("not json", encoding="utf-8")
    assert orphans.reap(tmp_path) is None
    assert not (tmp_path / orphans.RECORD).exists()


def test_recording_a_vanished_pid_writes_nothing(tmp_path: Path) -> None:
    orphans.record(tmp_path, 2**22 + 1)
    assert not (tmp_path / orphans.RECORD).exists()
