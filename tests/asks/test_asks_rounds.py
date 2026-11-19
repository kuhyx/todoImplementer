"""T2277: ask state belongs to the reply that asked, not to the bare id."""

from asksfakes import ID, Rig, Task
from todoimpl.asks import view
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
    assert states(rig) == {"logo_pixel": "open", "c9": "open"}
    got = {i["id"]: i for i in view.items("", load(rig.dir), rig.dir)}
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
