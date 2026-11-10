"""An umbrella through the service: one card, child rows from the child run dirs, the raw issue log."""

from pathlib import Path

import pytest
from contract_lib import validate
from servicefakes import Rig
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.service import ItemView
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.umbrella import issues
from todoimpl.umbrella.store import child_dir

BODY = """Umbrella: per-repo
Tier: cheap
- [ ] kuhyx/alpha (aaaa1111)
- [ ] kuhyx/beta (bbbb2222)
- [ ] kuhyx/gamma (cccc3333)
## kuhyx/alpha (aaaa1111)
# Alpha text
Scan textgate: 5 items
## kuhyx/beta (bbbb2222)
# Beta text
## kuhyx/gamma (cccc3333)
gamma
"""


def _record() -> dict[str, object]:
    kids = [
        {"id": "aaaa1111-0", "repo": "kuhyx/alpha", "title": "Alpha text", "done": False},
        {"id": "bbbb2222-0", "repo": "kuhyx/beta", "title": "Beta text", "done": False},
    ]
    rnd = {"n": 1, "width": 1, "next": 2, "children": []}
    return {"width": 2, "tier": "cheap", "kids": kids, "rounds": [rnd], "current": None}


def test_a_listed_umbrella_is_one_card_with_child_counts(rig: Rig) -> None:
    card_id = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    board = rig.backend.board()
    validate("board", board)
    (card,) = [c for c in board["tasks"] if c["id"] == card_id]
    assert (card["umbrella"]["total"], card["umbrella"]["queued"], card["status"]) == (3, 3, "backlog")


def test_a_registered_repo_less_umbrella_reaches_the_board(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_id = rig.fake.seed(None, "Make the repos text-free", BODY)
    file = tmp_path / "umbrellas.txt"
    file.write_text(note_id[:8] + "\n", encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(file))
    rig.backend.cache.refresh()
    card = rig.card(f"{note_id[:8]}-0")
    assert (card["repo"], card["status"], card["assignee"]) == (None, "backlog", "claude")
    assert "start" in [a["id"] for a in card["actions"] if a["enabled"]]


def test_the_drawer_lists_child_rows_rounds_and_issue_counts(rig: Rig) -> None:
    card_id = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    run = rig.run(card_id, "implement", worktree=str(rig.root / card_id), cost_usd=1.0)
    run.extra["umbrella"] = _record()
    save(run_dir(rig.root, card_id), run)
    child = RunState(task_id="aaaa1111-0", stage="gate", cost_usd=0.25)
    child.extra.update(verdict={"kind": "fixed", "detail": "x"}, free=True, umbrella_round=1)
    save(child_dir(run_dir(rig.root, card_id), "aaaa1111-0"), child)
    issues.append(run_dir(rig.root, card_id), 5.0, "kuhyx/alpha", "edit", "bad edit", "redid", fixed=True)
    rig.scheduler.live.add(card_id)
    detail = rig.backend.task(card_id)
    assert detail is not None
    validate("task", detail)
    rows = {r["id"]: r for r in detail["umbrella"]["rows"]}
    assert (rows["aaaa1111-0"]["status"], rows["aaaa1111-0"]["verdict"], rows["aaaa1111-0"]["issues"]) == (
        "ready_to_ship",
        "fixed",
        1,
    )
    assert rows["bbbb2222-0"]["status"] == "backlog"
    assert (detail["umbrella"]["width"], detail["umbrella"]["round"]) == (2, 1)
    card = detail["card"]
    assert card["cost_usd"] == 1.25
    assert (card["umbrella"]["ready"], card["umbrella"]["queued"], card["umbrella"]["issues"]) == (1, 1, 1)
    validate("board", rig.backend.board())


def test_the_issue_log_is_served_raw_and_unknown_tasks_give_none(rig: Rig) -> None:
    card_id = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    assert rig.backend.issues(card_id) == ""
    issues.append(run_dir(rig.root, card_id), 5.0, "kuhyx/alpha", "start", "no")
    text = rig.backend.issues(card_id)
    assert text is not None
    assert '"symptom": "no"' in text
    assert rig.backend.issues("ffffffff-0") is None


def test_item_view_ticks_a_child_in_the_umbrella_note(rig: Rig) -> None:
    card_id = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache).tick_child(card_id, "bbbb2222-0")
    text = next(iter(rig.fake.store.notes.values())).text
    assert "- [x] kuhyx/beta (bbbb2222)" in text


def test_t1921_cancel_never_abandons_an_umbrella_note(rig: Rig) -> None:
    card_id = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    view = ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache)
    assert view.abandon(card_id) is False
    (note,) = rig.fake.store.notes.values()
    assert note.status == "todo"
    assert "- [ ] kuhyx/alpha (aaaa1111)" in note.text
