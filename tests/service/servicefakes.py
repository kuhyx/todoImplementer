"""Test doubles and helpers for the service tests."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fake_todo_mcp import FakeTodoMcp
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.service import ServiceBackend


class FakeScheduler:
    """Records actions; `live` is what running() reports, `events` what subscribe yields."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.live: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.failure: Exception | None = None

    def _rec(self, *call: Any) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(call)

    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        self._rec("start", id8, auto_ship)

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

    def credits(self, id8: str) -> None:
        self._rec("credits", id8)

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
        """Seed a note, refresh the cache, return the card id of its first section."""
        note_id = self.fake.seed(repo, title, body, **f)
        self.backend.cache.refresh()
        return f"{note_id[:8]}-0"

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
