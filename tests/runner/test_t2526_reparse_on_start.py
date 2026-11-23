"""T2526: server start parses the questions again of every spec_wait card that stored none (older parser)."""

from __future__ import annotations

import json

from runnerfakes import Env, Notes
from todoimpl.board import state as store
from todoimpl.runner import recovery

REPLY = "Read the code.\n\n❓ **Q1 - Queued note**: What happens to it?\n➡️ Reopen the card.\n\nQ: answer it"


def _seed(
    world: Env, card: str, stage: str = "spec_wait", questions: list[store.SpecQuestion] | None = None
) -> None:
    st = store.RunState(
        task_id=card, stage=stage, repo="kuhyx/demo", last_tag="Q", spec_questions=questions or []
    )
    st.extra["last_reply"] = REPLY
    store.save(world.root / card, st)


def test_t2526_a_spec_wait_card_with_no_questions_gets_them_at_start(world: Env) -> None:
    _seed(world, "abcd1234-1")
    assert recovery.interrupted(world.root, Notes()) == []  # it still waits on kuhy: nothing is queued
    st = store.load(world.root / "abcd1234-1")
    assert st is not None
    assert [(q.id, q.title, q.body, q.recommendation) for q in st.spec_questions] == [
        ("Q1", "Queued note", "What happens to it?", "Reopen the card.")
    ]
    saved = json.loads((world.root / "abcd1234-1" / "questions.json").read_text(encoding="utf-8"))
    assert [q["id"] for q in saved] == ["Q1"]


def test_t2526_stored_questions_and_other_stages_are_left_alone(world: Env) -> None:
    _seed(world, "abcd1234-2", questions=[store.SpecQuestion("Q1", "Kept", "", "x", "x")])
    _seed(world, "abcd1234-3", stage="failed")
    recovery.interrupted(world.root, Notes())
    kept = store.load(world.root / "abcd1234-2")
    other = store.load(world.root / "abcd1234-3")
    assert kept is not None
    assert other is not None
    assert [q.title for q in kept.spec_questions] == ["Kept"]
    assert other.spec_questions == []
    assert not (world.root / "abcd1234-2" / "questions.json").exists()


def test_t2526_a_reply_with_no_cards_writes_nothing(world: Env) -> None:
    st = store.RunState(task_id="abcd1234-4", stage="spec_wait", repo="kuhyx/demo", last_tag="Q")
    st.extra["last_reply"] = "Q: which port?"
    store.save(world.root / "abcd1234-4", st)
    recovery.interrupted(world.root, Notes())
    assert not (world.root / "abcd1234-4" / "questions.json").exists()
