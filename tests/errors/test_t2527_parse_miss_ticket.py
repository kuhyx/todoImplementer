"""T2527: a question parser miss is one todoImplementer ticket; a second miss only raises its count."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from contract_lib import validate
from loopfakes import World
from todoimpl.errors.sources import Source
from todoimpl.runner import parsemiss
from todoimpl.runner.stream import TurnResult
from todoimpl.stall import report

MISS = "Looked.\n\n❓ Q1 / Scope — which file?\n➡️ hello.txt\n\nQ: answer it"
KEY = f"{report.APP}:{parsemiss.SIGNATURE}"


def _miss() -> None:
    driver: Any = SimpleNamespace(
        state=SimpleNamespace(task_id="abcd1234-1"), ctx=SimpleNamespace(now=lambda: 1.8e9)
    )
    parsemiss.check(driver, TurnResult(text=MISS, tag="Q", finished=True), "spec")


def test_t2527_a_parse_miss_becomes_one_ticket_and_a_second_raises_its_count(world: World) -> None:
    _miss()
    validate("app-error", json.loads(report.path().read_text(encoding="utf-8")), "report")
    board = Source(report.APP, "", "contract", report.path())
    world.loop.sources = lambda: [world.source, board]
    world.tick()
    (added,) = [a for a in world.tools("add_task") if a["repo"] == report.REPO]
    assert f"Error-Signature: {KEY}" in added["body"]
    assert world.ledger()[KEY]["count"] == 1
    _miss()
    world.tick()
    assert len([a for a in world.tools("add_task") if a["repo"] == report.REPO]) == 1
    assert world.ledger()[KEY]["count"] == 2  # the second miss
