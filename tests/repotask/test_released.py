"""T1994: a MANUAL WORK REQUIRED part whose asks kuhy answered is Claude's work again."""

from __future__ import annotations

import pytest
from repofakes import PLAN, Rig
from todoimpl.asks.service import AskService
from todoimpl.repotask.ids import repo_human_id
from todoimpl.runner.files import write_json
from todoimpl.runner.scheduler import RunnerError

BODY = """Encrypt it
```ask
choice c1: Key source | *password | keystore
choice c2: tutor client | *out of scope | in scope
```
"""


def _start(card: dict[str, object]) -> dict[str, object]:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next(a for a in actions if a["id"] == "start")


def test_t1994_a_manual_part_with_every_ask_answered_can_be_started(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "MANUAL WORK REQUIRED: encrypt payloads", BODY)
    hid = repo_human_id(repo)
    asks = AskService(rig.cache, rig.sched, rig.world.root)
    asks.answer(hid, "c1", "password")
    rig.cache.refresh()
    assert _start(rig.card(repo, human=True))["enabled"] is False  # c2 still open
    with pytest.raises(RunnerError, match="MANUAL WORK REQUIRED"):
        rig.sched.start(hid)
    asks.answer(hid, "c2", "in scope")  # not the recommended option
    rig.cache.refresh()
    card = rig.card(repo, human=True)
    assert card["title"] == "MANUAL WORK REQUIRED: encrypt payloads"
    assert (card["status"], card["assignee"]) == ("backlog", "claude")
    assert _start(card)["enabled"] is True
    assert [p["state"] for p in card["parts"]] == ["todo"]
    rig.script(hid, *[PLAN])
    rig.sched.start(hid)
    rig.until(lambda: bool(rig.world.calls()))
    prompt = str(rig.world.calls()[0])
    assert "Key source: password" in prompt
    assert "tutor client: in scope" in prompt


def test_t1995_an_answered_part_with_an_older_run_stays_on_the_human_card(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "MANUAL WORK REQUIRED: encrypt payloads", BODY)
    write_json(rig.run_dir(f"{note}-0") / "state.json", {"x": 1})  # an older run that counts as in flight
    hid = repo_human_id(repo)
    asks = AskService(rig.cache, rig.sched, rig.world.root)
    asks.take_recommended(hid)
    rig.cache.refresh()
    ids = [c["id"] for c in rig.backend.board()["tasks"]]
    assert f"{note}-0" not in ids  # not split off onto a card whose answers file is empty
    card = rig.card(repo, human=True)
    assert [p["state"] for p in card["parts"]] == ["todo"]
    assert _start(card)["enabled"] is True
