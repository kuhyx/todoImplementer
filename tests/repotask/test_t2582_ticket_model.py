"""T2582: other apps' error tickets run on Sonnet 5.5; kuhy's parts and his own pick keep their model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repofakes import IMPL, LIVE, PLAN, Rig
from todoimpl import modelpick
from todoimpl.board.state import RunState
from todoimpl.errors import ticket
from todoimpl.errors.record import AppError
from todoimpl.repotask import ticketmodel
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

RECORD = AppError("demo", "kuhyx/demo", "07626036aa", "crash", "boom", 1, "2026-11-27T00:00:00+00:00",
                  "2026-11-27T00:00:00+00:00", 0)  # fmt: skip
TICKET = f"## {ticket.title(RECORD)}\n{ticket.body(RECORD)}"


def _model(rig: Rig) -> str:
    return str(next(a["value"] for a in rig.card("kuhyx/demo")["actions"] if a["id"] == "model"))


def test_t2582_an_app_ticket_card_runs_and_shows_sonnet(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "demo errors", TICKET)
    card = repo_card_id(repo)
    assert _model(rig) == ticketmodel.MODEL  # the picker presses Sonnet before Start
    rig.script(card, PLAN, IMPL, LIVE)
    rig.sched.start(card)
    rig.until(lambda: len(rig.world.calls()) >= 2)
    assert [c["model"] for c in rig.world.calls()[:2]] == [ticketmodel.MODEL] * 2
    rig.sched.cancel(card)


def test_t2582_a_card_with_a_kuhy_part_runs_the_default_model(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "demo errors", TICKET + "\n\n## kuhy fix\nMake the kuhy fix.\ndone: it works")
    card = repo_card_id(repo)
    assert _model(rig) == modelpick.DEFAULT_MODEL
    rig.script(card, PLAN, IMPL, LIVE)
    rig.sched.start(card)
    rig.until(lambda: len(rig.world.calls()) >= 2)
    assert ticketmodel.MODEL not in [c["model"] for c in rig.world.calls()[:2]]
    rig.sched.cancel(card)


def test_t2582_the_mark_follows_the_parts_still_owed(tmp_path: Path) -> None:
    st = RunState(task_id="x-0", stage="implement", extra={ticketmodel.KEY: ticketmodel.MODEL})
    ticketmodel.mark(st, Item("abcd1234", 0, "kuhy", "Do it.", "kuhyx/demo", "todo", None), tmp_path)
    assert ticketmodel.of(st) is None
    st.extra[ticketmodel.KEY] = 3
    assert ticketmodel.of(st) is None
