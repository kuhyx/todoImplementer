"""T2527: a turn ending on `Q:` with a ❓ line no parser rule reads files one board error record."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from runnerfakes import Env
from schedfakes import CARD, boot, reply, wait_stage
from todoimpl.runner import parsemiss
from todoimpl.runner.stream import TurnResult
from todoimpl.stall import report

MISS = "Looked.\n\n❓ Q1 / Scope — which file?\n➡️ hello.txt\n\nQ: answer it"
GOOD = "Looked.\n\n❓ **Q1** - **Scope**: which file?\n➡️ hello.txt\n\nQ: answer it"


def _turn(text: str, tag: str = "Q") -> bool:
    driver: Any = SimpleNamespace(
        state=SimpleNamespace(task_id="abcd1234-1"), ctx=SimpleNamespace(now=lambda: 1.8e9)
    )
    return parsemiss.check(driver, TurnResult(text=text, tag=tag, finished=True), "implement")


def _records() -> list[dict[str, Any]]:
    if not report.path().exists():
        return []
    return [
        e
        for e in json.loads(report.path().read_text(encoding="utf-8"))["errors"]
        if e["signature"] == parsemiss.SIGNATURE
    ]


def test_t2527_an_unparsed_question_files_one_record_and_a_second_counts() -> None:
    assert _turn(MISS) is False  # the hook never resumes the session
    [record] = _records()
    assert (record["kind"], record["count"], record["repo"]) == ("parse.miss", 1, "kuhyx/todoImplementer")
    assert record["detail"] == "card abcd1234-1: ❓ Q1 / Scope — which file?"
    assert "60 s" not in record["message"]
    _turn(MISS)
    assert [r["count"] for r in _records()] == [2]


def test_t2527_parsed_cards_other_tags_and_plain_questions_file_nothing() -> None:
    _turn(GOOD)
    _turn(MISS, tag="D")
    _turn("Q: which port?")
    assert _records() == []


def test_t2527_a_spec_turn_that_misses_files_the_record(world: Env) -> None:
    sched, _ = boot(world, reply(MISS), body="Make it nicer")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "spec_wait")
        assert st.spec_questions == []
        assert [r["detail"] for r in _records()] == [f"card {CARD}: ❓ Q1 / Scope — which file?"]
    finally:
        sched.close()
