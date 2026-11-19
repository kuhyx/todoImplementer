"""A note sent while the reply's choices are still open carries the ones kuhy already answered (T2275)."""

import pytest
from servicefakes import Rig
from todoimpl.asks import store
from todoimpl.board.state import run_dir

REPLY = """Q: pick below.

```ask
choice colour: Colour | Mono | *Gold | risk=reversible
choice next: What next? | *Refine | Wider round | risk=reversible
screenshot sheet: The sheet | shots/a.png
```"""


def _answered(rig: Rig, card: str, **answers: str) -> None:
    directory = run_dir(rig.root, card)
    data = store.load(directory)
    for ask_id, answer in answers.items():
        data["items"][ask_id] = {"state": "answered", "answer": answer, "at": 1.0}
    store.save(directory, data)


def test_t2275_a_note_carries_the_answers_that_wait_for_the_other_choices(rig: Rig) -> None:
    rig.run("t1", "implement", session_id="s", extra={"last_reply": REPLY})
    _answered(rig, "t1", colour="Mono")
    rig.backend.send("t1", "Thanks, now an interactive way")
    assert rig.scheduler.calls == [
        ("send", "t1", "Thanks, now an interactive way\n\n(runner) kuhy answered in the note: Colour: Mono")
    ]


@pytest.mark.parametrize("answers", [{}, {"colour": "Mono", "next": "Refine"}])
def test_t2275_no_answer_or_one_already_delivered_leaves_the_note_as_typed(
    rig: Rig, answers: dict[str, str]
) -> None:
    rig.run("t1", "implement", session_id="s", extra={"last_reply": REPLY})
    _answered(rig, "t1", **answers)
    rig.backend.send("t1", "plain note")
    assert rig.scheduler.calls == [("send", "t1", "plain note")]


def test_t2275_a_card_with_no_run_sends_the_note_as_typed(rig: Rig) -> None:
    rig.backend.send("t1", "plain note")
    assert rig.scheduler.calls == [("send", "t1", "plain note")]
