"""T2114: answers saved on a repo's former human card (`<hash>-1`, T1980) move onto its one card once."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.asks import store
from todoimpl.repotask import foldasks
from todoimpl.repotask.ids import former_human_id, repo_card_id
from todoimpl.repotask.legacy import Older
from todoimpl.service.repocards import group_cards, released_in
from todoimpl.todo_mcp.model import Task

if TYPE_CHECKING:
    from pathlib import Path

REPO = "kuhyx/teatr"
ASK = "Send it\n```ask\nchoice c1: When | *wait | now\nchoice c2: Export | *later | export now\n```\n"
MANUAL = "MANUAL WORK REQUIRED: mail two people"


def notes(manual_body: str = ASK) -> list[Task]:
    return [
        Task("aaaa1111", "site", "## fix the site\nx", REPO, "todo", "medium", None),
        Task("bbbb2222", MANUAL, manual_body, REPO, "todo", "medium", None),
    ]


def answered(*ids: str) -> dict[str, object]:
    items = {i: {"state": "answered", "answer": f"old {i}", "at": 1.0} for i in ids}
    return {"seen": dict.fromkeys(ids, 0.5), "items": items, "log": ["sweep: ask block added"]}


def old_answers(root: Path, *ids: str) -> Path:
    directory = root / former_human_id(REPO)
    store.save(directory, answered(*ids))
    return directory


def test_t2114_answers_on_the_former_human_card_release_the_part_on_the_repo_card(tmp_path: Path) -> None:
    old_answers(tmp_path, "c1", "c2")
    foldasks.fold_all(tmp_path, notes())
    (card,) = group_cards(notes(), lambda _key: Older(), released_in(tmp_path))
    assert card.id == repo_card_id(REPO)
    manual = next(p for p in card.parts if p.manual)
    assert (manual.human, manual.actionable) == (False, True)  # both asks answered: Claude's work (T1994)
    data = store.load(tmp_path / repo_card_id(REPO))
    assert data["items"]["c2"]["answer"] == "old c2"
    assert data["seen"] == {"c1": 0.5, "c2": 0.5}


def test_the_repo_cards_own_record_wins_and_a_closed_notes_ask_stays_behind(tmp_path: Path) -> None:
    old = answered("c1", "c2", "c9")  # c9 belongs to a manual note closed long ago
    old["seen"] = {}  # an answer whose first-seen time was never saved still moves
    store.save(tmp_path / former_human_id(REPO), old)
    own = {"seen": {}, "items": {"c1": {"state": "answered", "answer": "mine", "at": 2.0}}, "log": []}
    store.save(tmp_path / repo_card_id(REPO), own)
    assert foldasks.fold_all(tmp_path, notes()) == [repo_card_id(REPO)]
    data = store.load(tmp_path / repo_card_id(REPO))
    assert data["items"]["c1"]["answer"] == "mine"
    assert data["items"]["c2"]["answer"] == "old c2"
    assert "c9" not in data["items"]
    assert data["log"][-1].startswith(f"fold: c2 from {former_human_id(REPO)}")


def test_a_rerun_or_a_later_answer_on_the_old_card_changes_nothing(tmp_path: Path) -> None:
    old = old_answers(tmp_path, "c1")
    assert foldasks.fold_all(tmp_path, notes()) == [repo_card_id(REPO)]
    before = (tmp_path / repo_card_id(REPO) / store.FILE).read_text(encoding="utf-8")
    store.save(old, answered("c1", "c2"))
    assert foldasks.fold_all(tmp_path, notes()) == []
    assert (tmp_path / repo_card_id(REPO) / store.FILE).read_text(encoding="utf-8") == before
    assert (old / store.FILE).is_file()  # the old run dir is never deleted


def test_repos_without_old_answers_or_open_manual_asks_write_nothing(tmp_path: Path) -> None:
    assert foldasks.fold_all(tmp_path, notes()) == []
    old_answers(tmp_path, "c1")
    others = [Task("cccc3333", "x", "y", None, "todo", "medium", None), *notes("do it by hand")]
    assert foldasks.fold_all(tmp_path, others) == []
    assert not (tmp_path / repo_card_id(REPO)).exists()
    assert (tmp_path / former_human_id(REPO) / foldasks.MARK).is_file()  # decided once, on the notes open now
