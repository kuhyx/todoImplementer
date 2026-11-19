"""An all_repos note becomes an umbrella with one child per repo the change touches, found by `git grep`."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Triage
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.todo_mcp.model import TodoError
from todoimpl.triage import label, umbrella
from todoimpl.triage.classify import parse
from todoimpl.umbrella import note as umbrella_note

Make = Callable[..., Triage]
ALL = {"label": "all_repos", "token": "freshness", "path": ".github", "reason": "every repo with the check"}
TITLE = "get rid of github ci/cd version check of package leave it only locally"


def clone(src: Path, name: str, files: dict[str, str]) -> None:
    """Make a real local clone of kuhyx/<name>: git init, the files in the index (git grep reads those)."""
    path = src / name
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)


@pytest.fixture
def clones(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    ci = ".github/workflows/dependency-freshness.yml"
    clone(src, "screen-locker", {ci: "run: scripts/check_dependency_freshness.sh\n", "README.md": "x"})
    clone(src, "utils", {".github/workflows/ci.yml": "run: make test\n", "notes.txt": "freshness"})
    return src


def test_t2072_a_note_for_all_repos_becomes_an_umbrella_with_the_repos_that_have_the_check(
    rig: Rig, triage: Make, clones: Path
) -> None:
    card = rig.note(TITLE, repo=None)
    assert triage(ALL).service.tick() == 1
    shown = rig.card(card)
    found = umbrella_note.children(rig.backend.cache.snapshot().tasks[0].body, card[:8])
    assert [(c.repo, c.key, c.cid) for c in found] == [("kuhyx/screen-locker", card[:8], f"{card[:8]}-1")]
    assert TITLE in found[0].text  # the ask rides in every child
    assert (shown["id"], shown["repo"], shown["status"]) == (card, None, "backlog")
    assert shown["umbrella"]["total"] == 1
    assert label.load(run_dir(rig.root, card))["repos"] == ["kuhyx/screen-locker"]  # type: ignore[index]
    assert "kuhyx/utils" not in rig.backend.cache.snapshot().tasks[0].body  # notes.txt is outside .github


def test_t2072_children_of_one_note_get_distinct_run_ids_and_boxes(
    rig: Rig, triage: Make, clones: Path
) -> None:
    card = rig.note(TITLE, "details", repo=None)
    triage({"label": "all_repos", "reason": "all"}).service.tick()  # no token: every cloned repo
    body = rig.backend.cache.snapshot().tasks[0].body
    kids = umbrella_note.children(body, card[:8])
    assert sorted(c.repo for c in kids) == ["kuhyx/screen-locker", "kuhyx/utils"]
    assert sorted(c.cid for c in kids) == [f"{card[:8]}-1", f"{card[:8]}-2"]
    assert [c.label for c in kids] == [f"{card[:8]}-0", f"{card[:8]}-1"]
    ticked = umbrella_note.tick(body, kids[1].label)
    assert [c.done for c in umbrella_note.children(ticked, card[:8])] == [False, True]
    assert "details" in kids[0].text


def test_t2072_no_matching_repo_means_no_umbrella_and_the_note_stays_yours(
    rig: Rig, triage: Make, clones: Path
) -> None:
    card = rig.note(TITLE, repo=None)
    triage({**ALL, "token": "nothing-has-this"}).service.tick()
    rig.backend.cache.refresh()
    shown = rig.card(card)
    assert (shown["status"], shown["triage"]) == ("yours", "all_repos")
    assert label.load(run_dir(rig.root, card))["error"] == "no repo matches"  # type: ignore[index]
    assert "umbrella" not in shown


def test_t2072_a_refused_umbrella_write_is_kept_as_an_error(
    rig: Rig, triage: Make, clones: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = rig.note(TITLE, repo=None)
    run = triage(ALL)

    def refuse(*_a: object, **_k: object) -> None:
        msg = "body: refused"
        raise TodoError(msg)

    monkeypatch.setattr(run.service.client, "update_task", refuse)
    run.service.tick()
    assert label.load(run_dir(rig.root, card))["error"] == "body: refused"  # type: ignore[index]


def test_t2072_has_token_reads_a_missing_hit_a_bad_dir_and_a_timeout_as_no(
    clones: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = clones / "screen-locker"
    assert umbrella.has_token(repo, "freshness", ".github")
    assert umbrella.has_token(repo, "freshness", None)
    assert not umbrella.has_token(repo, "freshness", "README.md")
    assert not umbrella.has_token(repo, "freshness", "no-such-dir")
    assert not umbrella.has_token(tmp_path, "freshness", None)  # not a git repo
    monkeypatch.setattr(umbrella, "TIMEOUT_S", 1e-9)
    assert not umbrella.has_token(repo, "freshness", None)


def test_t2072_the_prompt_lists_the_ci_file_names_with_how_many_repos_have_each(
    rig: Rig, triage: Make, clones: Path
) -> None:
    rig.note(TITLE, repo=None)
    run = triage(ALL)
    run.service.tick()
    assert "ci.yml (1), dependency-freshness.yml (1)" in run.prompts[0]
    both = ["kuhyx/screen-locker", "kuhyx/utils"]
    assert umbrella.workflow_names(both, lambda r: clones / r.split("/")[1], 1) == ["ci.yml (1)"]
    assert umbrella.workflow_names(["kuhyx/gone"], lambda _r: clones / "gone") == []


def test_t2072_a_path_must_stay_inside_the_repo() -> None:
    repos = ["kuhyx/a"]
    for path, kept in [(".github", ".github"), ("../x", None), ("-x", None), ("a b", None)]:
        reply = f'{{"label":"all_repos","token":"t","path":"{path}"}}'
        assert parse(reply, repos).path == kept
