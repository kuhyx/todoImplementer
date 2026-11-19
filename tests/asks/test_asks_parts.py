"""T1992: a repo card has an empty body; its asks live in its parts."""

from asksfakes import BODY, ID, PartBody, Rig, Task
from todoimpl.asks import store, view
from todoimpl.asks.view import DAY
from todoimpl.board.state import RunState, save


def test_t1992_ask_block_in_a_part_of_a_repo_card(rig: Rig) -> None:
    rig.cache.tasks[:] = [Task(ID, "", (PartBody(BODY), PartBody(BODY.replace("c1", "z9"))))]
    got = view.items("", None, rig.dir, rig.cache.tasks[0].parts)
    assert [i["id"] for i in got] == ["c1", "c2", "k1", "s1", "z9"]
    rig.svc.answer(ID, "z9", "red")
    assert rig.svc.adopt_due() == 0


def test_t2114_a_manual_parts_asks_show_beside_the_runs_newest_reply(rig: Rig) -> None:
    """The run's reply asks hide the work text's asks, never kuhy's manual parts on the same card."""
    run = RunState(task_id=ID, stage="implement", extra={"last_reply": "```ask\ncommand z1: ls\n```"})
    manual = PartBody(BODY.replace("c1", "m1"), manual=True)
    got = view.items("", run, rig.dir, Task(ID, "", (PartBody(BODY), manual)).parts)
    assert [i["id"] for i in got] == ["z1", "m1", "c2", "k1", "s1"]


REPLY = "```ask\nchoice z1: Port | *8080 | 9090\nchoice z2: Name | *a | b | risk=reversible\n```"
MANUAL = (
    "Mail them\n```ask\nchoice m1: Send | *wait | now | risk=reversible\n"
    "screenshot s9: Sent? | shots/m.png\n```"
)


def mixed(rig: Rig) -> None:
    """Seed a repo card whose run asks z1, z2 in its reply, beside a manual part asking m1."""
    rig.cache.tasks[:] = [Task(ID, "", (PartBody(MANUAL, manual=True),))]
    rig.dir.mkdir(parents=True)
    save(rig.dir, RunState(task_id=ID, stage="implement", extra={"last_reply": REPLY}))


def test_t2114_the_session_hears_its_answers_while_a_manual_ask_stays_open(rig: Rig) -> None:
    mixed(rig)
    rig.svc.take_recommended(ID)  # the session's choices only: m1 would release kuhy's work
    assert [text for _id, text in rig.sched.sent] == [
        "(runner) kuhy answered in the note: Port: 8080; Name: a"
    ]
    assert store.load(rig.dir)["items"].keys() == {"z1", "z2"}
    rig.svc.answer(ID, "m1", "now")  # kuhy's own decision: no news for the session
    rig.svc.verdict(ID, "s9", approve=True)
    assert len(rig.sched.sent) == 1


def test_t2114_auto_adopt_tells_the_session_only_of_its_own_asks(rig: Rig) -> None:
    mixed(rig)
    rig.svc.answer(ID, "z1", "9090")
    assert rig.sched.sent == []  # z2 is still open
    assert rig.svc.adopt_due() == 0
    rig.clock.now += 2 * DAY
    assert rig.svc.adopt_due() == 2  # z2 and m1, both reversible
    assert [text for _id, text in rig.sched.sent] == ["(runner) kuhy answered in the note: Name: a (auto)"]
