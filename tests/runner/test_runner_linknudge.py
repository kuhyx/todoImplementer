"""T2135: an `A:` that says "open /page" with no host goes back to its session to show it in the task."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from todoimpl.board.state import RunState
from todoimpl.runner import askform, linknudge

OPEN = "Built it.\n\nA: Open /logo-lab and pick the logo you like."
LIVE = "Live at https://kuhy.duckdns.org.\n\nA: Open /logo-lab and pick the logo you like."
BLOCK = "A: pick\n\n```ask\nchoice c1: Logo | a | *b | risk=reversible\n```\nOpen /logo-lab."


def _driver(text: str, **extra: Any) -> tuple[Any, list[int]]:
    saved: list[int] = []
    st = RunState(task_id="x-0", stage="implement", last_tag="A", extra={"last_reply": text, **extra})
    return SimpleNamespace(state=st, activity=lambda _t: None, save=lambda: saved.append(1)), saved


def _res(tag: str = "A") -> Any:
    return SimpleNamespace(tag=tag, is_error=False, denials=[])


def test_t2135_an_ask_to_open_a_bare_route_is_sent_back() -> None:
    driver, saved = _driver(OPEN)
    assert linknudge.needs_link(driver, _res(), "implement")
    note = driver.state.extra["granted_note"]
    assert saved == [1]
    assert "/logo-lab" in note
    assert "full absolute URL" in note
    assert "```ask block" in note
    assert "screenshot" in note
    assert driver.state.extra[linknudge.KEY] == 1


def test_t2135_a_route_with_a_known_host_is_left_alone() -> None:
    driver, saved = _driver(LIVE)
    assert not linknudge.needs_link(driver, _res(), "implement")
    assert saved == []


def test_t2135_a_reply_with_an_ask_block_is_left_alone() -> None:
    driver, _ = _driver(BLOCK)
    assert not linknudge.needs_link(driver, _res(), "implement")


@pytest.mark.parametrize("stage", ["spec", "plan"])
def test_t2135_stages_that_edit_nothing_are_left_alone(stage: str) -> None:
    driver, _ = _driver(OPEN)
    assert not linknudge.needs_link(driver, _res(), stage)


def test_t2135_other_tags_errors_phone_waits_and_unattended_runs_are_left_alone() -> None:
    driver, _ = _driver(OPEN)
    assert not linknudge.needs_link(driver, _res("R"), "implement")
    broken = _res()
    broken.is_error = True
    assert not linknudge.needs_link(driver, broken, "implement")
    waiting, _ = _driver(OPEN, waiting_phone={"criteria": ["C7"]})
    assert not linknudge.needs_link(waiting, _res(), "implement")
    child, _ = _driver(OPEN, umbrella_round=1)
    assert not linknudge.needs_link(child, _res(), "implement")


def test_t2135_two_send_backs_per_run() -> None:
    spent, _ = _driver(OPEN, **{linknudge.KEY: linknudge.MAX_NUDGES})
    assert not linknudge.needs_link(spent, _res(), "implement")


def test_t2135_the_ask_form_note_comes_first_and_the_two_never_share_a_turn() -> None:
    driver, _ = _driver(OPEN)
    assert askform.needs_form(driver, _res(), "implement")
    assert linknudge.KEY not in driver.state.extra
    form_note = driver.state.extra["granted_note"]
    assert "full absolute URL" in form_note
    spent, _ = _driver(OPEN, **{askform.RUN_KEY: askform.MAX_FORMS_RUN})
    assert not askform.needs_form(spent, _res(), "implement")
    assert linknudge.needs_link(spent, _res(), "implement")
