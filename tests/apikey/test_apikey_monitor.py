import logging
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from apikeyfakes import KEY
from fake_todo_mcp import FakeTodoMcp
from todoimpl.apikey import store
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.apikey.monitor import COMMAND, REPO, TITLE, KeyMonitor
from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.client import TodoClient

OK = KeyStatus("ok", date(2026, 12, 1), "fine")
EXPIRED = KeyStatus("expired", date(2026, 11, 1), "expired on 2026-11-01")
INVALID = KeyStatus("invalid", date(2026, 12, 1), "rejected")


class Rig:
    def __init__(self, fake: FakeTodoMcp, root: Path) -> None:
        self.fake, self.root = fake, root
        self.client = TodoClient(fake.url, fake.token)
        self.current = OK
        self.monitor = self.make()

    def make(self, **kw: object) -> KeyMonitor:
        return KeyMonitor(
            self.client,
            check=lambda _today: self.current,
            clock=lambda: date(2026, 11, 8),
            **kw,  # type: ignore[arg-type]
        )

    def open_titles(self) -> list[str]:
        out = []
        for note in self.client.list_tasks(repo=REPO, full=True):
            out += [c.title for c in card_tasks(note) if c.status != "done"]
        return out


@pytest.fixture
def rig(fake: FakeTodoMcp, tmp_path: Path) -> Rig:
    return Rig(fake, tmp_path / "run")


def test_latest_is_none_before_the_first_tick(rig: Rig) -> None:
    assert rig.monitor.latest() is None
    rig.monitor.tick()
    assert rig.monitor.latest() == OK


def test_title_and_command_are_exact() -> None:
    assert TITLE == "MANUAL WORK REQUIRED: rotate Claude API key"
    assert COMMAND == "~/src/todoImplementer/scripts/rotate_api_key.py"


def test_ok_creates_nothing(rig: Rig) -> None:
    rig.monitor.tick()
    assert rig.open_titles() == []


def test_not_ok_creates_the_task_once_with_state_expiry_and_command(rig: Rig) -> None:
    rig.current = EXPIRED
    rig.monitor.tick()
    rig.monitor.tick()
    assert rig.open_titles() == [TITLE]
    body = next(c.body for n in rig.client.list_tasks(repo=REPO, full=True) for c in card_tasks(n))
    assert "expired" in body
    assert "2026-11-01" in body
    assert COMMAND in body


def test_task_is_closed_when_the_status_is_ok_again(rig: Rig) -> None:
    rig.current = EXPIRED
    rig.monitor.tick()
    rig.current = OK
    rig.monitor.tick()
    assert rig.open_titles() == []
    assert "rotate_api_key" not in " ".join(rig.open_titles())
    note = next(iter(rig.fake.store.notes.values()))
    assert note.status == "done"
    assert "ok" in (note.evidence or "")


def test_a_second_failure_after_recovery_makes_a_new_task(rig: Rig) -> None:
    for status in (EXPIRED, OK, INVALID):
        rig.current = status
        rig.monitor.tick()
    assert rig.open_titles() == [TITLE]


def test_other_open_sections_of_the_note_are_left_alone(rig: Rig) -> None:
    rig.client.add_task(REPO, "something else", "x")
    rig.current = EXPIRED
    rig.monitor.tick()
    rig.current = OK
    rig.monitor.tick()
    assert rig.open_titles() == ["something else"]


def test_todo_mcp_down_is_logged_and_the_status_is_still_kept(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.fake.stop()
    rig.current = EXPIRED
    with caplog.at_level(logging.WARNING):
        rig.monitor.tick()
    assert "todo" in caplog.text
    assert rig.monitor.latest() == EXPIRED


def test_no_task_is_attempted_twice_per_tick_when_ok_and_mcp_down(rig: Rig) -> None:
    rig.fake.stop()
    rig.monitor.tick()  # ok: closing needs the MCP, which is down: logged, not raised
    assert rig.monitor.latest() == OK


def test_a_crashing_check_is_survived(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    def boom(_today: date) -> KeyStatus:
        raise RuntimeError("kaboom")

    monitor = KeyMonitor(rig.client, check=boom)
    with caplog.at_level(logging.ERROR):
        monitor.tick()
    assert "kaboom" in caplog.text
    assert monitor.latest() is None


def test_default_check_reads_the_real_files_through_the_verifier(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("todoimpl.apikey.keystatus.verify", lambda _k: pytest.fail("no key: no call"))
    monitor = KeyMonitor(TodoClient(fake.url, fake.token))
    monitor.tick()
    latest = monitor.latest()
    assert latest is not None
    assert latest.state == "missing"


def test_loop_ticks_at_start_and_when_a_key_file_changes(rig: Rig) -> None:
    ticks = threading.Event()
    seen: list[int] = []

    def check(_today: date) -> KeyStatus:
        seen.append(1)
        ticks.set()
        return OK

    monitor = KeyMonitor(rig.client, check=check, interval=3600.0, poll=0.01)
    monitor.start()
    monitor.start()  # idempotent
    assert ticks.wait(5)
    time.sleep(0.1)
    assert len(seen) == 1  # an hour has not passed and nothing changed
    ticks.clear()
    store.save(KEY, date(2026, 11, 8), date(2026, 12, 8))
    assert ticks.wait(5)
    monitor.stop()
    assert len(seen) == 2


def test_loop_ticks_again_after_the_interval(rig: Rig) -> None:
    count = threading.Semaphore(0)

    def check(_today: date) -> KeyStatus:
        count.release()
        return OK

    monitor = KeyMonitor(rig.client, check=check, interval=0.05, poll=0.01)
    monitor.start()
    assert count.acquire(timeout=5)
    assert count.acquire(timeout=5)
    monitor.stop()


def test_stop_without_start_is_fine(rig: Rig) -> None:
    rig.monitor.stop()


def test_after_write_fires_only_when_a_task_was_created_or_closed(rig: Rig) -> None:
    writes: list[int] = []
    monitor = rig.make(after_write=lambda: writes.append(1))
    monitor.tick()  # ok, no task: nothing written
    rig.current = EXPIRED
    monitor.tick()  # created
    monitor.tick()  # already there
    rig.current = OK
    monitor.tick()  # closed
    monitor.tick()
    assert len(writes) == 2
