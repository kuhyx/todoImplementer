"""Test doubles and helpers for the service tests."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fake_todo_mcp import FakeTodoMcp
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.repotask.ids import repo_card_id
from todoimpl.service import ServiceBackend
from todoimpl.umbrella.note import is_umbrella


class FakeScheduler:
    """Records actions; `live` is what running() reports, `events` what subscribe yields."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.live: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.failure: Exception | None = None
        self.extras: list[dict[str, Any] | None] = []

    def _rec(self, *call: Any) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(call)

    def start(self, id8: str, *, auto_ship: bool | None = None, extra: dict[str, Any] | None = None) -> None:
        self._rec("start", id8, auto_ship)
        self.extras.append(extra)

    def spec_answers(self, id8: str, answers: dict[str, str]) -> None:
        self._rec("spec_answers", id8, answers)

    def spec_ok(self, id8: str) -> None:
        self._rec("spec_ok", id8)

    def send(self, id8: str, text: str) -> None:
        self._rec("send", id8, text)

    def ship(self, id8: str) -> None:
        self._rec("ship", id8)

    def cancel(self, id8: str) -> None:
        self._rec("cancel", id8)

    def close_item(self, id8: str) -> None:
        self._rec("close_item", id8)

    def done_manually(
        self, id8: str, *, repo: str | None = None, title: str = "", repotask: bool = False
    ) -> None:
        self._rec("done_manually", id8, repo, title, repotask)

    def auto_start(self, id8: str, passed_at: float) -> bool:
        self._rec("auto_start", id8, passed_at)
        return True

    def running(self) -> set[str]:
        return set(self.live)

    def subscribe(self, id8: str) -> Iterator[dict[str, Any]]:
        return iter(self.events)


@dataclass
class Rig:
    """Everything a service test touches."""

    fake: FakeTodoMcp
    backend: ServiceBackend
    scheduler: FakeScheduler
    root: Path

    def note(
        self, title: str = "demo todos", body: str = "", repo: str | None = "kuhyx/demo", **f: str | None
    ) -> str:
        """Seed a note, refresh the cache, return its card id (the repo task's; `<id8>-0` without a repo)."""
        note_id = self.fake.seed(repo, title, body, **f)
        self.backend.cache.refresh()
        if not repo or is_umbrella(body):
            return f"{note_id[:8]}-0"
        return repo_card_id(repo)  # manual parts too: one card per repo (T2114)

    def sections(self, body: str, repo: str | None = "kuhyx/demo", title: str = "demo todos") -> list[str]:
        """Seed a note whose every section has an older run in flight (so each keeps its own section card)."""
        note_id = self.fake.seed(repo, title, body)
        count = sum(1 for line in body.split("\n") if line.startswith("## "))
        ids = [f"{note_id[:8]}-{i}" for i in range(max(count, 1))]
        for card in ids:
            self.run(card, "gate")
        self.backend.cache.refresh()
        return ids

    def run(self, task_id: str, stage: str = "implement", **fields: Any) -> RunState:
        """Write a state.json for a card."""
        state = RunState(task_id=task_id, stage=stage, **fields)
        save(run_dir(self.root, task_id), state)
        return state

    def card(self, task_id: str) -> dict[str, Any]:
        """Return the board card of one task."""
        return next(c for c in self.backend.board()["tasks"] if c["id"] == task_id)


def write_stream(directory: Path, skills: list[str]) -> None:
    """Write a stream file whose Skill tool_use events name these skills."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}
        )
        for name in skills
    ]
    (directory / "implement-1.000.stream.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


Runner = Callable[[], None]
