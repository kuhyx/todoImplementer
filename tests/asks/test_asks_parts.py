"""T1992: a repo card has an empty body; its asks live in its parts."""

from asksfakes import BODY, ID, PartBody, Rig, Task
from todoimpl.asks import view


def test_t1992_ask_block_in_a_part_of_a_repo_card(rig: Rig) -> None:
    rig.cache.tasks[:] = [Task(ID, "", (PartBody(BODY), PartBody(BODY.replace("c1", "z9"))))]
    got = view.items("", None, rig.dir, rig.cache.tasks[0].parts)
    assert [i["id"] for i in got] == ["c1", "c2", "k1", "s1", "z9"]
    rig.svc.answer(ID, "z9", "red")
    assert rig.svc.adopt_due() == 0
