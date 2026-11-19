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
        return [gone, *real(base)] if len(calls) <= 2 else real(base)

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
