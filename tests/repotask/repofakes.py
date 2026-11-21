"""A repo-task world: a fake todo MCP, the board cache over it, the real Scheduler and ServiceBackend."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from runnerfakes import Env, make_repo
from todoimpl.board import state as store
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.scheduler import Scheduler
from todoimpl.service import ItemView, ServiceBackend, TaskCache, board_fetch
from todoimpl.todo_mcp.client import TodoClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from fake_todo_mcp import FakeTodoMcp

PLAN = (
    {
        "_fake": "result",
        "text": "## Approach\n- do it\n## Acceptance criteria\nC1. I run it, I see it\n\nD: planned",
    },
)
IMPL = (
    {"_fake": "write", "path": "hello.txt", "text": "hi\n"},
    {"_fake": "result", "text": "C1: done - saw it\n\nD: done"},
)
LIVE = ({"_fake": "result", "text": "- [x] C1: ran it -> saw it\n\nD: done"},)


def live_for(*keys: str) -> tuple[dict[str, str], ...]:
    """Return a live check passing one criterion per part key (a keyed card needs one per part, T2447)."""
    rows = "".join(f"- [x] C{i} [{key}]: ran it -> saw it\n" for i, key in enumerate(keys, 1))
    return ({"_fake": "result", "text": f"{rows}\nD: done"},)


@dataclass
class Rig:
    """Everything a repo-task test touches."""

    world: Env
    fake: FakeTodoMcp
    client: TodoClient
    cache: TaskCache
    sched: Scheduler
    backend: ServiceBackend

    def repo(self, name: str = "demo") -> str:
        """Make the clone `~/src/<name>` and return the repo spelling notes use."""
        make_repo(self.world, name)
        return f"kuhyx/{name}"

    def note(self, repo: str | None, title: str, body: str = "", **fields: str | None) -> str:
        """Seed an open note and refresh the board cache; return the note's 8-char id."""
        note_id = self.fake.seed(repo, title, body, **fields)
        self.cache.refresh()
        return note_id[:8]

    def card(self, repo: str) -> dict[str, Any]:
        """Return the board card of the repo's task: Claude's parts and the manual ones (T2114)."""
        wanted = repo_card_id(repo)
        return next(c for c in self.backend.board()["tasks"] if c["id"] == wanted)

    def run_dir(self, card: str) -> Path:
        """Return the run dir of a card."""
        return self.world.root / card

    def state(self, card: str) -> store.RunState:
        """Return the saved run state of a card."""
        found = store.load(self.run_dir(card))
        assert found is not None
        return found

    def wait(self, card: str, stages: set[str], timeout: float = 30.0) -> store.RunState:
        """Block until the card's run rests in one of `stages`."""
        end = time.time() + timeout
        while time.time() < end:
            st = store.load(self.run_dir(card))
            if st is not None and st.stage in stages and card not in self.sched.running():
                return st
            time.sleep(0.05)
        msg = f"{card} did not reach {stages}: {store.load(self.run_dir(card))}"
        raise AssertionError(msg)

    def until(self, check: Callable[[], bool], timeout: float = 30.0) -> None:
        """Block until `check()` is true."""
        end = time.time() + timeout
        while time.time() < end:
            if check():
                return
            time.sleep(0.05)
        msg = "condition not reached"
        raise AssertionError(msg)

    def script(self, card: str, *turns: tuple[dict[str, Any], ...]) -> None:
        """Queue fake-claude turns for a card's run."""
        for turn in turns:
            self.world.script(card.partition("-")[0], *turn)


def build_rig(world: Env, fake: FakeTodoMcp) -> Rig:
    """Wire the cache, the real Scheduler (check timeout 20 s) and the backend over the fake MCP."""
    client = TodoClient(fake.url, fake.token)
    cache = TaskCache(board_fetch(client, world.root))
    sched = Scheduler(ItemView(client, cache, world.root), world.root, check_timeout=20)
    return Rig(world, fake, client, cache, sched, ServiceBackend(cache, sched, world.root, "b1"))
