"""T2376: a reply that asks only what kuhy already answered this cycle gets his answers back at once.

Without this the card rests in Needs you with every button already answered and nothing left to click.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from todoimpl.asks import store
from todoimpl.board.state import RunState
from todoimpl.runner import answered

REAL = json.loads((Path(__file__).parents[1] / "fixtures" / "kalisz_reasks.json").read_text("utf-8"))
FIVE, ANSWERS = REAL["five_again_reply"], REAL["answers"]


def _driver(run_dir: Path, text: str) -> tuple[Any, list[int]]:
    saved: list[int] = []
    st = RunState(task_id="x-0", stage="implement", last_tag="A", extra={"last_reply": text})
    driver = SimpleNamespace(
        state=st, ctx=SimpleNamespace(run_dir=run_dir), activity=lambda _t: None, save=lambda: saved.append(1)
    )
    return driver, saved


def _res(tag: str = "A") -> Any:
    return SimpleNamespace(tag=tag, is_error=False, denials=[])


def _clicked(run_dir: Path) -> None:
    """Kuhy's six clicks on the reply before (another round), as AskService saves them."""
    items = {k: {"state": "answered", "answer": v, "at": 1.0, "cycle": 1} for k, v in ANSWERS.items()}
    store.save(run_dir, {"seen": {}, "items": items, "rounds": dict.fromkeys(ANSWERS, "older"), "log": []})


def test_t2376_a_reask_of_answered_choices_resumes_with_his_answers(tmp_path: Path) -> None:
    _clicked(tmp_path)
    driver, saved = _driver(tmp_path, FIVE)
    assert answered.back(driver, _res(), "implement")
    note = str(driver.state.extra["granted_note"])
    assert [v for k, v in ANSWERS.items() if k != "selection" and v not in note] == []
    assert saved == [1]
    assert answered.back(driver, _res(), "implement")
    assert not answered.back(driver, _res(), "implement")  # twice per run, then it rests


def test_t2376_an_open_ask_or_another_tag_is_left_alone(tmp_path: Path) -> None:
    driver, saved = _driver(tmp_path, FIVE)
    assert not answered.back(driver, _res(), "implement")  # nothing answered yet: kuhy has buttons
    _clicked(tmp_path)
    assert not answered.back(driver, _res("D"), "implement")
    assert not answered.back(driver, _res(), "plan")
    driver.state.extra["last_reply"] = "A: no block"
    assert not answered.back(driver, _res(), "implement")
    assert saved == []
