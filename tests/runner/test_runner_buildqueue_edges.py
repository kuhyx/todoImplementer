"""Edges of the build-lock queue and the hold ceiling: files that vanish, gone pids (T2164, T2166)."""

from __future__ import annotations

import fcntl
import io
import subprocess
import threading
import time
from pathlib import Path

import pytest
from todoimpl.runner import buildlock, buildqueue, holdceiling


def test_t2164_a_bypasser_on_build_lock_still_excludes_and_the_wait_is_said_once(tmp_path: Path) -> None:
    base = buildlock.root()
    queue = base / buildqueue.QUEUE
    queue.mkdir(parents=True)
    (queue / ".new.4242").write_text("")  # a crash between create and rename
    out = io.StringIO()
    ran = threading.Event()
    with (queue / "000000000001").open("w") as ticket, (base / buildlock.LOCK).open("a") as lock:
        ticket.write("1 held ? (x) since 2026-11-19 10:00:00\n")
        ticket.flush()
        fcntl.flock(ticket, fcntl.LOCK_EX)
        fcntl.flock(lock, fcntl.LOCK_EX)  # a hand-held lock, as an old wrapper would hold it

        def board() -> None:
            with buildlock.held("card-b", "make test", out):
                ran.set()

        thread = threading.Thread(target=board)
        thread.start()
        deadline = time.monotonic() + 10
        while not out.getvalue() or (queue / ".new.4242").exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        fcntl.flock(ticket, fcntl.LOCK_UN)
        time.sleep(0.3)
        assert not ran.is_set()  # the ticket is gone, but build.lock still excludes
    thread.join(10)
    assert ran.is_set()
    assert out.getvalue().count("waiting for build lock") == 1
    assert out.getvalue().endswith("; 1 ahead\n")


def test_t2164_files_that_vanish_mid_look_are_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = tmp_path / "000000000004"
    assert buildqueue._parse(gone) == buildqueue.Ticket(4, 0, "wait", "?", "", "")
    real = buildqueue.tickets
    calls: list[int] = []

    def flaky(base: Path) -> list[Path]:
        calls.append(1)
        return [gone, *real(base)] if len(calls) <= 3 else real(base)

    monkeypatch.setattr(buildqueue, "tickets", flaky)
    assert buildqueue.listing(tmp_path) == []
    calls.clear()
    with buildlock.held("card-c", "make", 0):  # the vanished earlier ticket is passed over
        pass


def test_t2166_a_gone_process_samples_as_nothing_and_is_never_signalled() -> None:
    dead = subprocess.Popen(["true"])
    dead.wait()
    assert holdceiling._sample(dead.pid) == (0.0, 0, frozenset({dead.pid}), False)
    events: list[object] = []
    sink = type("Sink", (), {"bus": type("Bus", (), {"publish": lambda *a: events.append(a)})()})()
    ceiling = holdceiling.Ceiling(sink)
    ceiling._cut(buildqueue.Ticket(1, dead.pid, "held", "card-d", "make", ""), buildlock.root())
    assert events == []


def test_t2168_a_settled_file_swapped_or_gone_under_the_cleaner_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "000000000007"
    path.write_text("1 wait ? (x) since 2026-11-19 10:00:00\n")
    with path.open("rb") as fh:
        path.unlink()
        assert buildqueue._settle(path, fh) is False  # gone
        path.write_text("2 wait ? (y) since 2026-11-19 10:00:00\n")
        assert buildqueue._settle(path, fh) is False  # a new ticket under the old name
    assert path.read_text().startswith("2 wait")


def test_t2168_a_live_twin_an_expired_place_or_a_vanished_one_is_never_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = buildlock.root()
    queue = base / buildqueue.QUEUE
    queue.mkdir(parents=True)
    (queue / "000000000001").write_text("9 gone c1-0 (make test) since 2026-11-19 10:00:00 board\n")
    old = time.time() - buildqueue.RESERVE - 1
    import os  # noqa: PLC0415 - only this test ages a file

    os.utime(queue / "000000000001", (old, old))
    with (queue / "000000000002").open("w") as twin:
        twin.write("9 wait c1-0 (make test) since 2026-11-19 10:00:00 board\n")
        twin.flush()
        fcntl.flock(twin, fcntl.LOCK_EX)  # the same check, alive in another thread
        assert buildqueue._claim(base, "c1-0", "make test") is None
    assert not (queue / "000000000001").exists()
    ghost = buildqueue.Ticket(5, 9, "gone", "c1-0", "make test", "", board=True)
    monkeypatch.setattr(buildqueue, "tickets", lambda _base: [queue / "000000000005"])
    monkeypatch.setattr(buildqueue, "_parse", lambda _path: ghost)
    assert buildqueue._claim(base, "c1-0", "make test") is None
