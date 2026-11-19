"""T1992: a repo card has an empty body; its asks live in its parts."""

from asksfakes import BODY, ID, PartBody, Rig, Task
from todoimpl.asks import view
from todoimpl.board.state import RunState


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
