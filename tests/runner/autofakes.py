"""Auto-close test helpers: a temp trust file, the settings switch, and a poller over a FakeClient."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from todoimpl.runner.autocheck import AutoCloser
from todoimpl.service.cards import card_tasks

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env, FakeClient
    from todoimpl.runner.autocheck import Starter
    from todoimpl.service.cards import CardTask


def trust_file(world: Env) -> Path:
    """Return the temp HOME's trust file (the real default location under that HOME)."""
    return world.home / ".config" / "todo-hooks" / "trusted-checks"


def trust(world: Env, *checks: str) -> None:
    """Write the trust file listing exactly these checks, in todo-hooks' own line format."""
    path = trust_file(world)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{hashlib.sha256(c.strip().encode()).hexdigest()}  # test {i}" for i, c in enumerate(checks)]
    path.write_text("# trusted\n\n" + "".join(r + "\n" for r in rows), encoding="utf-8")


def switch(world: Env, *, on: bool | None) -> None:
    """Write settings.json with auto_close on/off, or without the key (None)."""
    world.root.mkdir(parents=True, exist_ok=True)
    body = {} if on is None else {"auto_close": on}
    (world.root / "settings.json").write_text(json.dumps(body), encoding="utf-8")


def arm(world: Env, *checks: str) -> None:
    """Trust the checks and turn the switch on with a recorded (empty) baseline."""
    trust(world, *checks)
    switch(world, on=True)
    (world.root / "autocheck.json").write_text("{}", encoding="utf-8")


def cache(world: Env) -> dict[str, Any]:
    """Return autocheck.json."""
    data: dict[str, Any] = json.loads((world.root / "autocheck.json").read_text(encoding="utf-8"))
    return data


def cards_of(client: FakeClient) -> list[CardTask]:
    """Every section of every note of the fake client as a card."""
    return [card for note in client.tasks.values() for card in card_tasks(note)]


def poller(world: Env, starter: Starter, client: FakeClient, **kwargs: Any) -> AutoCloser:
    """Return an AutoCloser over the client's cards (no thread; tests call tick())."""
    return AutoCloser(world.root, lambda: cards_of(client), starter, **kwargs)


class Starts:
    """A Starter that records each auto-start and answers `result`."""

    def __init__(self, *, result: bool = True) -> None:
        self.result = result
        self.calls: list[str] = []

    def auto_start(self, card: str, passed_at: float) -> bool:
        assert passed_at > 0
        self.calls.append(card)
        return self.result
