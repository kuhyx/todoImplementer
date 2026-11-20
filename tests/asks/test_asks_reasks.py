"""T2376: kuhy answered six choices, the session heard one of them and asked the other five again, twice.

The replies and answers are card 1c1ca49b-0's own (tests/fixtures/kalisz_reasks.json).
"""

import json
from pathlib import Path

from asksfakes import ID, Rig, Task
from todoimpl.asks import store, view
from todoimpl.board.state import RunState, load, save

REAL = json.loads((Path(__file__).parents[1] / "fixtures" / "kalisz_reasks.json").read_text("utf-8"))
SIX, FIVE, ANSWERS = REAL["six_questions_reply"], REAL["five_again_reply"], REAL["answers"]
VERDICT = "Mail\n```ask\nchoice c2: Send this mail? | *approve | change\n```"


def reply(rig: Rig, text: str, cycle: int = 1) -> None:
    """Make `text` the run's newest reply, as the runner does after a turn."""
    rig.cache.tasks[:] = [Task(ID, "")]
    rig.dir.mkdir(parents=True, exist_ok=True)
    save(rig.dir, RunState(task_id=ID, stage="implement", extra={"last_reply": text, "cycle": cycle}))


def shown(rig: Rig) -> dict[str, tuple[str, str | None]]:
    """Return what the card shows per ask: its state and answer."""
    return {i["id"]: (i["state"], i.get("answer")) for i in view.items("", load(rig.dir), rig.dir)}


def answer_all(rig: Rig) -> None:
    for ask_id, option in ANSWERS.items():
        rig.svc.answer(ID, ask_id, option)


def test_t2376_the_session_hears_every_answer_of_the_round(rig: Rig) -> None:
    reply(rig, SIX)
    answer_all(rig)
    assert len(rig.sched.sent) == 1
    told = rig.sched.sent[0][1]
    assert [option for option in ANSWERS.values() if option not in told] == []


def test_t2376_a_choice_asked_again_this_cycle_keeps_kuhys_answer(rig: Rig) -> None:
    reply(rig, SIX)
    answer_all(rig)
    reply(rig, FIVE)
    want = {k: ("answered", v) for k, v in ANSWERS.items() if k != "selection"}
    assert shown(rig) == want
    rig.svc.adopt_due()  # the 5-min tick saved asks.json and so erased them on the live card
    assert shown(rig) == want
    assert store.load(rig.dir)["items"]["surface"]["answer"] == ANSWERS["surface"]


def test_t2376_a_new_cycle_or_changed_options_ask_afresh(rig: Rig) -> None:
    reply(rig, SIX)
    answer_all(rig)
    reply(rig, SIX.replace(ANSWERS["history"], "autosave as plain text"))  # kuhy's option is gone
    assert shown(rig)["history"] == ("open", None)
    assert shown(rig)["surface"] == ("answered", ANSWERS["surface"])
    reply(rig, FIVE, cycle=2)
    assert {state for state, _ in shown(rig).values()} == {"open"}


def test_t2376_a_change_on_an_approval_is_asked_again_an_approve_is_not(rig: Rig) -> None:
    reply(rig, VERDICT)
    rig.svc.answer(ID, "c2", "change")
    reply(rig, VERDICT.replace("Mail", "Mail, edited"))
    assert shown(rig) == {"c2": ("open", None)}  # the edited mail is a new thing to judge
    rig.svc.answer(ID, "c2", "approve")
    reply(rig, VERDICT.replace("Mail", "Mail, sent?"))
    assert shown(rig) == {"c2": ("answered", "approve")}
