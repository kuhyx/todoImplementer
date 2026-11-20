"""Hermetic fixtures for the triage tests: the service rig (fake todo MCP, fake scheduler) and a triage."""

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent / "shims"))

from fake_todo_mcp import FakeTodoMcp  # noqa: E402
from servicefakes import FakeScheduler, Rig  # noqa: E402
from todoimpl.service import ServiceBackend, build_backend  # noqa: E402
from todoimpl.todo_mcp.client import TodoClient  # noqa: E402
from todoimpl.triage.service import TriageService  # noqa: E402

REPOS = ["kuhyx/todoImplementer", "kuhyx/screen-locker", "kuhyx/utils"]


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture
def rig(fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "src"))
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "run"))
    backend: ServiceBackend = build_backend(
        root=tmp_path / "run",
        build="b1",
        client=TodoClient(fake.url, fake.token),
        scheduler=FakeScheduler(),
        refresh=False,
    )
    yield Rig(fake, backend, backend.scheduler, tmp_path / "run")  # type: ignore[arg-type]
    backend.cache.stop()


class Triage:
    """A TriageService whose classifier replays `replies` and records the prompts it was given.

    New repos are made by `provision` (a fake that records its calls) and every background job runs inline.
    """

    def __init__(self, rig: Rig, replies: list[object]) -> None:
        self.prompts: list[str] = []
        self.replies = replies
        self.now = 1000.0
        self.created: list[dict[str, object]] = []
        self.provision_error: Exception | None = None
        self.jobs: list[Callable[[], None]] | None = None  # a list holds the jobs instead of running them
        self.service = TriageService(
            TodoClient(rig.fake.url, rig.fake.token),
            rig.backend.cache,
            rig.root,
            scheduler=rig.scheduler,
            classifier=self._ask,
            repos=lambda: REPOS,
            clock=lambda: self.now,
            spawn=self._spawn,
            provision=self._provision,
            src=rig.root.parent / "src",
        )
        rig.backend.triage_service = self.service

    def _spawn(self, job: Callable[[], None]) -> None:
        if self.jobs is None:
            job()
        else:
            self.jobs.append(job)

    def _provision(self, directory: Path, src: Path, **facts: object) -> str:
        if self.provision_error is not None:
            raise self.provision_error
        self.created.append({**facts, "dir": str(directory), "src": str(src)})
        return f"kuhyx/{facts['name']}"

    def _ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


@pytest.fixture
def triage(rig: Rig) -> Callable[..., Triage]:
    def make(*replies: object) -> Triage:
        return Triage(rig, list(replies))

    return make
