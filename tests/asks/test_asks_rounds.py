"""T2277: ask state belongs to the reply that asked, not to the bare id."""

from asksfakes import ID, Rig, Task
from todoimpl.asks import store, view
from todoimpl.asks.view import DAY
from todoimpl.board.state import RunState, load, save

FIRST = (
    "Round one\n```ask\nscreenshot logo_pixel: Pixel logo ok? | shots/a.png\nchoice c9: Mode | *a | b\n```"
)
SECOND = FIRST.replace("Round one", "Round two").replace("Pixel logo", "New pixel logo")


def reply(rig: Rig, text: str) -> None:
    """Make `text` the run's newest reply, as the runner does after a turn."""
    rig.cache.tasks[:] = [Task(ID, "")]
    rig.dir.mkdir(parents=True, exist_ok=True)
    save(rig.dir, RunState(task_id=ID, stage="implement", extra={"last_reply": text}))


def states(rig: Rig) -> dict[str, str]:
    run = load(rig.dir)
    return {i["id"]: i["state"] for i in view.items("", run, rig.dir)}


def test_t2277_a_reused_id_in_a_new_reply_is_a_fresh_ask(rig: Rig) -> None:
    reply(rig, FIRST)
    rig.svc.verdict(ID, "logo_pixel", approve=False)
    rig.svc.answer(ID, "c9", "b")
    assert states(rig) == {"logo_pixel": "rejected", "c9": "answered"}
    reply(rig, SECOND)
    # A shot is a new picture to judge; a choice kuhy answered this cycle keeps his answer (T2376).
    assert states(rig) == {"logo_pixel": "open", "c9": "answered"}
    reply(rig, SECOND.replace("| b", "| c"))  # his option is gone: a new question
    got = {i["id"]: i for i in view.items("", load(rig.dir), rig.dir)}
    assert got["c9"]["state"] == "open"
    assert "answer" not in got["c9"]
    assert view.held("", load(rig.dir), rig.dir) == []


def test_t2277_the_same_reply_keeps_its_answers(rig: Rig) -> None:
    reply(rig, FIRST)
    rig.svc.answer(ID, "c9", "b")
    assert states(rig)["c9"] == "answered"
    rig.svc.verdict(ID, "logo_pixel", approve=True)
    assert states(rig) == {"logo_pixel": "approved", "c9": "answered"}


def test_t2277_a_new_round_restarts_the_24_h_auto_adopt_clock(rig: Rig) -> None:
    rev = "```ask\nchoice r1: Pick | *a | b | risk=reversible\n```"
    reply(rig, "one\n" + rev)
    assert rig.svc.adopt_due() == 0  # first seen now
    rig.clock.now += DAY - 10
    reply(rig, "two\n" + rev)
    assert rig.svc.adopt_due() == 0  # new round: clock starts again
    rig.clock.now += 20
    assert rig.svc.adopt_due() == 0
    rig.clock.now += DAY
    assert rig.svc.adopt_due() == 1


def test_t2277_a_record_saved_before_rounds_is_adopted_not_dropped(rig: Rig) -> None:
    reply(rig, FIRST)
    old = {"state": "answered", "answer": "b", "at": 1.0}
    store.save(rig.dir, {"seen": {"c9": 5.0}, "items": {"c9": old}, "log": []})
    assert states(rig)["c9"] == "answered"  # no `rounds` entry: kept, not erased on deploy
    rig.svc.verdict(ID, "logo_pixel", approve=True)  # a write stamps the round
    data = store.load(rig.dir)
    assert data["items"]["c9"]["answer"] == "b"
    assert data["seen"]["c9"] == 5.0
    assert data["rounds"]["c9"] == data["rounds"]["logo_pixel"] != ""
    reply(rig, SECOND)
    assert states(rig)["c9"] == "open"  # a different reply still starts fresh
