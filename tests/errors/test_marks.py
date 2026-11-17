"""The marks of an error run: which parts may ship by themselves and who answers no questions."""

from __future__ import annotations

from todoimpl.board.state import RunState
from todoimpl.errors import marks
from todoimpl.repotask.model import Part
from todoimpl.umbrella import bounce


def part(key: str, body: str) -> Part:
    return Part(key, key[:8], 0, f"t {key}", body, "medium", None, human=False, held=False)


def run(**extra: object) -> RunState:
    return RunState(task_id="abcd1234-0", stage="implement", extra=dict(extra))


MARK = {"app_error": {"reason": "weekly", "keys": ["a:1"]}}


def test_signatures_are_the_signature_lines_of_a_text() -> None:
    assert marks.signatures(
        "x\n  Error-Signature: a:1  \nError-Signature: b:2\nnot Error-Signature: c:3"
    ) == ["a:1", "b:2"]
    assert marks.signatures("") == []


def test_an_error_run_is_the_one_the_loop_started() -> None:
    assert marks.is_error_run(run(**MARK)) is True
    assert marks.is_error_run(run()) is False


def test_t2025_it_ships_itself_only_when_every_ticked_part_is_an_error_part() -> None:
    mine = part("aaaa1111-0", "Error-Signature: a:1")
    other = part("bbbb2222-1", "kuhy's own part")
    assert marks.ships_itself(run(**MARK), [mine], "") is True
    assert marks.ships_itself(run(**MARK), [mine, other], "") is False  # kuhy's work waits at the gate
    assert marks.ships_itself(run(**MARK), [], "x\nError-Signature: a:1") is True  # a plain note
    assert marks.ships_itself(run(**MARK), [], "no signature") is False
    assert marks.ships_itself(run(), [mine], "") is False  # not an error run


def test_t2026_an_error_run_answers_to_no_one_like_an_umbrella_child() -> None:
    st = run(**MARK)
    assert bounce.is_child(st) is True
    assert bounce.again(st) is True
    assert bounce.check_cap(st, 2) == bounce.MAX_CHILD_CHECK_FIXES
    assert bounce.is_child(run()) is False
    assert marks.unattended(st) is True
    assert marks.unattended(run(umbrella_round=1)) is True
    assert marks.unattended(run()) is False
