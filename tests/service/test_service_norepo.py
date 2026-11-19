"""Open todo notes without a repo are cards too: the Yours lane (DOCS-features.md), never dropped."""

import time

from contract_lib import validate
from servicefakes import Rig
from todoimpl.service import TaskCache, board_fetch
from todoimpl.todo_mcp.client import TodoClient


def test_t2058_an_open_note_without_a_repo_is_a_yours_card_in_backlog(rig: Rig) -> None:
    idea = rig.note("wysłać jpk", repo=None)
    board = rig.backend.board()
    validate("board", board)
    card = rig.card(idea)
    assert (card["title"], card["repo"], card["status"], card["column"]) == (
        "wysłać jpk",
        None,
        "yours",
        "backlog",
    )
    assert [a["id"] for a in card["actions"]] == ["wont", "done-manually"]  # never startable
    assert board["repos"] == []


def test_t2058_each_section_of_a_repo_less_note_is_its_own_card(rig: Rig) -> None:
    note = rig.fake.seed(None, "ideas", "## first\na\n\n## second\nb")
    rig.backend.cache.refresh()
    tasks = rig.backend.board()["tasks"]
    assert {c["title"] for c in tasks} == {"first", "second"}
    assert {c["id"] for c in tasks} == {f"{note[:8]}-0", f"{note[:8]}-1"}


def test_t2058_closed_and_abandoned_repo_less_notes_stay_off_the_board(rig: Rig) -> None:
    rig.fake.seed(None, "finished", status="done")
    rig.fake.seed(None, "dropped", status="abandoned")
    rig.note("kept", repo=None)
    assert [c["title"] for c in rig.backend.board()["tasks"]] == ["kept"]


def test_t2058_repo_and_repo_less_notes_share_the_board(rig: Rig) -> None:
    repo_card = rig.note("demo todos", "## a\nx")
    idea = rig.note("an idea", repo=None)
    assert {c["id"] for c in rig.backend.board()["tasks"]} == {repo_card, idea}


def test_t2051_a_note_added_in_the_todo_app_reaches_the_board_within_the_refresh_loop(rig: Rig) -> None:
    client = TodoClient(rig.fake.url, rig.fake.token)
    cache = TaskCache(board_fetch(client, rig.root), interval=0.05)
    cache.start()
    try:
        card = f"{rig.fake.seed(None, 'brand new idea')[:8]}-0"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(c.id == card for c in cache.snapshot().tasks):
            time.sleep(0.02)
        assert any(c.id == card for c in cache.snapshot().tasks)
    finally:
        cache.stop()
