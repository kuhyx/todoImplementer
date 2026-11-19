"""Shared rig of the research-card tests: a fake todo client, replayed turns and a run dir."""

import json
from pathlib import Path
from typing import Any

import pytest
from todoimpl.asks import store
from todoimpl.board.state import RunState, load
from todoimpl.runner.pipeline import Ctx, Driver
from todoimpl.runner.stream import TurnResult
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import TodoError
from todoimpl.triage import research
from todoimpl.triage.label import RESEARCH, Verdict, save
from todoimpl.triage.research import ResearchDriver
from todoimpl.umbrella.driver import driver_for

ASK = (
    "```ask\n"
    "choice c1: Add a feed digest to kuhylog | Make note | *Skip | risk=reversible\n"
    "choice c2: New app | Make note | *Skip | risk=reversible\n"
    "```\nA:"
)
ACTIONS = [
    {"id": "c1", "title": "Digest in kuhylog", "repo": "kuhyx/kuhylog", "body": "Add it. Done: it shows."},
    {"id": "c2", "title": "New reader app", "repo": None, "body": "Build it. Done: it runs."},
]


class Client:
    """The part of the todo view a research run uses."""

    def __init__(self) -> None:
        self.added: list[tuple[str, str, str]] = []
        self.closed: list[tuple[str, str]] = []
        self.fail = False

    def add_task(self, repo: str, title: str, body: str = "") -> Any:
        if self.fail:
            raise TodoError("todo app down")
        self.added.append((repo, title, body))
        return type("T", (), {"id": "abcdef0123456789"})()

    def close_task(self, card: str, evidence: str) -> None:
        self.closed.append((card, evidence))


class Rig:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.dir = tmp_path / "f206969c-0"
        self.dir.mkdir(parents=True)
        self.client = Client()
        self.replies: list[TurnResult] = []
        self.turns = 0
        self.umbrellas: list[str] = []
        monkeypatch.setattr(research, "create_umbrella", self._umbrella)
        monkeypatch.setattr(ResearchDriver, "turn", lambda driver, *_a, **_k: self._turn(driver))
        self.item = Item("f206969c", 0, "https://paulgraham.com/google.html", "", None, "todo", None, "kuhy")
        self.state = RunState("f206969c-0", "spec", repo=None)

    def _umbrella(self, text: str) -> str:
        self.umbrellas.append(text)
        return "99999999-aaaa"

    def _turn(self, driver: Driver) -> TurnResult:
        self.turns += 1
        res = self.replies.pop(0)
        driver.state.extra["last_reply"] = res.text
        return res

    def ctx(self) -> Ctx:
        return Ctx(
            self.dir.parent, self.dir, self.client, lambda _e: None, lambda _h: None, lambda: 5.0,
            lambda: False, 1.0, list,
        )  # fmt: skip

    def drive(self) -> RunState:
        save(self.dir, Verdict(RESEARCH), "d", 1.0)
        driver_for(self.ctx(), self.state, self.item).run()
        return load(self.dir)  # type: ignore[return-value]

    def answer(self, **picks: str) -> None:
        data = store.load(self.dir)
        data["items"] = {key: {"state": "answered", "answer": value} for key, value in picks.items()}
        store.save(self.dir, data)


@pytest.fixture(name="rig")
def research_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(tmp_path, monkeypatch)


def report(rig: Rig, actions: object = ACTIONS) -> None:
    (rig.dir / "research.md").write_text("Key ideas: many.", encoding="utf-8")
    (rig.dir / "research.json").write_text(json.dumps(actions), encoding="utf-8")
