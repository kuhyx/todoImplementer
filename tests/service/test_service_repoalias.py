"""T2272: one board entry per real repo, keyed by its checkout's origin, never a guessed owner."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fake_todo_mcp import FakeTodoMcp
from servicefakes import Rig
from todoimpl.board import repos
from todoimpl.board.repos import canonical
from todoimpl.http.newtask import NewTask
from todoimpl.newtask.service import NewTaskService
from todoimpl.repotask.ids import repo_card_id
from todoimpl.service import repoalias
from todoimpl.todo_mcp.model import Task, TodoError

REAL, GUESS = "Sepci0/cleanup-plate", "kuhyx/cleanup-plate"


def clone(src: Path, name: str, url: str | None) -> Path:
    """Make `<src>/<name>` look like a git checkout whose origin is `url` (none: no remote)."""
    (src / name / ".git").mkdir(parents=True)
    if url:
        (src / name / ".git" / "config").write_text(f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8")
    return src / name


def shipped(rig: Rig, card: str, repo: str, updated: float = 0.0) -> None:
    """Write the shipped run of a repo task under `card`."""
    extra = {"repotask": True, "repotask_title": "cleanup-plate"}
    rig.run(card, "shipped", repo=repo, updated=updated, extra=extra)


@pytest.fixture
def src(tmp_path: Path) -> Path:
    """~/src of the rig ($TODOIMPL_SRC) with cleanup-plate checked out from Sepci0."""
    clone(tmp_path / "src", "cleanup-plate", f"https://github.com/{REAL}.git")
    return tmp_path / "src"


def test_t2272_a_folder_guessed_owner_joins_the_real_repos_one_card(
    rig: Rig, fake: FakeTodoMcp, src: Path
) -> None:
    guessed = fake.seed(GUESS, "cleanup-plate todos", "## from the feedback inbox\nx")
    fake.seed(REAL, "cleanup-plate todos", "## from kuhy\ny")
    rig.backend.cache.refresh()
    board = rig.backend.board()
    assert board["repos"] == [REAL]
    cards = [c for c in board["tasks"] if "cleanup-plate" in (c["repo"] or "")]
    assert [(c["id"], c["repo"]) for c in cards] == [(repo_card_id(REAL), REAL)]
    assert len(rig.card(repo_card_id(REAL))["parts"]) == 2
    assert fake.store.notes[guessed].repo == REAL  # migrated through update_task: per-repo reads find it


def test_t2272_shipped_runs_under_both_names_are_one_done_card(
    rig: Rig, fake: FakeTodoMcp, src: Path
) -> None:
    shipped(rig, repo_card_id(GUESS), GUESS, 2.0)  # newer, but the real name's own dir wins
    shipped(rig, repo_card_id(REAL), REAL, 1.0)
    shipped(rig, "ffffffff-0", GUESS, 0.5)  # read last, ranks lower: dropped
    old = fake.seed(GUESS, "cleanup-plate todos", "## a section run\nz", status="done")
    rig.run(f"{old[:8]}-0", "shipped")  # a closed note's section card, before repo tasks
    rig.backend.cache.refresh()
    board = rig.backend.board()
    assert board["repos"] == [REAL]
    assert [c["id"] for c in board["tasks"] if c["id"].endswith("-0") and c["title"] == "cleanup-plate"] == [
        repo_card_id(REAL)
    ]
    assert rig.card(f"{old[:8]}-0")["repo"] == REAL


def test_t2272_an_alias_run_alone_shows_under_the_real_name(rig: Rig, src: Path) -> None:
    shipped(rig, repo_card_id(GUESS), GUESS)
    rig.backend.cache.refresh()
    assert rig.card(repo_card_id(GUESS))["repo"] == REAL


def test_t2272_a_new_task_typed_with_the_guessed_owner_files_under_the_real_one(
    rig: Rig, fake: FakeTodoMcp, src: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path / "images"))
    api = rig.backend.new_task_service
    assert isinstance(api, NewTaskService)
    note, card = api.create(NewTask(GUESS, "Fix the plate", "", ()))
    assert card == repo_card_id(REAL)
    assert next(n.repo for n in fake.store.notes.values() if n.id.startswith(note)) == REAL


def test_t2272_only_a_hosted_origin_of_the_checkout_renames(src: Path) -> None:
    clone(src, "local", str(src.parent / "remotes" / "local.git"))  # a bare-path remote names no owner
    clone(src, "bare", None)
    clone(src, "Mixed", "git@github.com:kuhyx/Mixed.git")
    assert canonical("kuhyx/local", src) == "kuhyx/local"
    assert canonical("kuhyx/bare", src) == "kuhyx/bare"
    assert canonical("kuhyx/missing", src) == "kuhyx/missing"
    assert canonical("cleanup-plate", src) == REAL  # a bare name is kuhyx/<name>, which runs there
    assert canonical("kuhyx/mixed", src) == "kuhyx/Mixed"
    assert canonical("Other/cleanup-plate", src) == "Other/cleanup-plate"  # not its clone (T2000)


def test_t2272_answers_are_kept_until_refresh(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(repos, "_clock", lambda: now[0])
    assert canonical("kuhyx/later", src) == "kuhyx/later"
    clone(src, "later", "https://github.com/Someone/later")
    assert canonical("kuhyx/later", src) == "kuhyx/later"
    now[0] += repos.REFRESH_S
    assert canonical("kuhyx/later", src) == "Someone/later"


class _Refusing:
    def update_task(self, id8: str, **fields: str | None) -> Task:
        msg = f"{id8} {fields} refused"
        raise TodoError(msg)


def test_t2272_a_refused_rewrite_still_shows_the_real_name(
    src: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    notes = [
        Task("aaaa1111", "t", "", GUESS, "todo", "medium", None),
        Task("bbbb2222", "t", "", "sepci0/Cleanup-Plate", "todo", "medium", None),  # case only: rewritten
        Task("cccc3333", "t", "", None, "todo", "medium", None),
    ]
    with caplog.at_level(logging.WARNING, "todoimpl.service"):
        healed = repoalias.heal(_Refusing(), notes)  # type: ignore[arg-type]
    assert [n.repo for n in healed] == [REAL, REAL, None]
    assert [r.message[5:13] for r in caplog.records] == ["aaaa1111", "bbbb2222"]
