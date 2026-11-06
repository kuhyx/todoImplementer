"""build_backend starts the phone watcher of a scheduler that has one."""

from pathlib import Path

from servicefakes import FakeScheduler
from todoimpl.service import build_backend
from todoimpl.todo_mcp.client import TodoClient


class WatchingScheduler(FakeScheduler):
    started = 0

    def start_phone_watch(self) -> None:
        self.started += 1


def test_t1550_the_service_starts_the_phone_watcher_once(tmp_path: Path) -> None:
    sched = WatchingScheduler()
    backend = build_backend(
        root=tmp_path, build="x", client=TodoClient("http://127.0.0.1:1/mcp", "t"), scheduler=sched
    )
    backend.cache.stop()
    assert sched.started == 1
