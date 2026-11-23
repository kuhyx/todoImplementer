"""T2514: stray work origin lacks becomes a ticket for Claude; work origin already holds needs nothing."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from runnerfakes import Env, make_repo, sh
from schedfakes import CARD
from todoimpl.errors import sources, ticket
from todoimpl.errors.sources import state_base
from todoimpl.runner import deploy, deployheal, stray, worktree

LINES = "".join(f"{n}\n" for n in "abcdefg")  # far apart edits merge without a conflict


def _repo(world: Env, old: str, new: str) -> tuple[Path, Path, Path]:
    """Push `lib.txt` going from `old` to `new`; return (worktree, run dir, kuhy's checkout)."""
    md = "# demo\n\n## Commands\n\n- deploy: `true`\n"
    checkout = make_repo(world, files={"CLAUDE.md": md, "lib.txt": old})
    wt = worktree.add(checkout, world.root, CARD).path
    (wt / "lib.txt").write_text(new, encoding="utf-8")
    sh(wt, "git", "commit", "-qam", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    return wt, world.root / CARD, checkout


def _stray(checkout: Path, files: dict[str, str]) -> None:
    """Leave edits a free worker wrote, at rest long enough to count as strays."""
    for name, text in files.items():
        (checkout / name).write_text(text, encoding="utf-8")
        os.utime(checkout / name, (time.time() - deployheal.QUIET - 60,) * 2)


def _filed() -> list[dict[str, Any]]:
    path = state_base() / "app-errors" / stray.FILE
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


def _pull(checkout: Path) -> str:
    return f"git -C {checkout} pull -q --ff-only"


def _refusing(checkout: Path) -> str:
    """Return a deploy that refuses any dirty checkout: every dirty file counts, untracked ones too."""
    return f'test -z "$(git -C {checkout} status --porcelain)" || {{ echo "{checkout} is dirty"; exit 1; }}'


def test_t2514_stray_work_origin_lacks_becomes_one_ticket_for_claude(world: Env) -> None:
    wt, run_dir, checkout = _repo(world, "old\n", "new\n")
    _stray(checkout, {"lib.txt": "stray\n", "extra.txt": "a new file\n"})
    done = deploy.run(wt, run_dir, CARD, "demo", _refusing(checkout))
    assert done.passed
    (patch,) = (run_dir / "deploy").glob("stray-*.patch")
    text = patch.read_text(encoding="utf-8")
    assert "+stray" in text
    assert "+a new file" in text  # the untracked file is in the patch, not only in the stash
    (row,) = _filed()
    assert (row["app"], row["repo"], row["kind"], row["count"]) == ("demo", "kuhyx/demo", stray.KIND, 1)
    assert row["signature"].endswith(stray.SUFFIX)
    sha = sh(checkout, "git", "stash", "list", "--format=%H").split()[0]
    assert str(patch) in row["detail"]
    assert sha in row["detail"]
    assert f"{row['app']}:{row['signature']}" in done.tail  # the close evidence names the ticket
    validate("app-error", json.loads((state_base() / "app-errors" / stray.FILE).read_text()), "report")
    (parsed,) = [r for _s, r in sources.records(sources.configured()) if r.kind == stray.KIND]
    assert parsed.key == f"demo:{row['signature']}"  # the errors loop reads it: a ticket on the repo's card
    body = ticket.body(parsed)
    assert "Fix this error" not in body
    assert f"git stash apply {sha}" in body
    assert "Do not ask kuhy" in body


def test_t2514_the_same_stray_patch_twice_is_one_ticket_counted_twice(world: Env) -> None:
    wt, run_dir, checkout = _repo(world, "old\n", "new\n")
    _stray(checkout, {"lib.txt": "stray\n"})
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo", _pull(checkout)).passed
    (row,) = _filed()
    (patch,) = (run_dir / "deploy").glob("stray-*.patch")
    stray.report("kuhyx/demo", patch, "0" * 40, ["lib.txt"], time.time())
    (again,) = _filed()
    assert (again["signature"], again["count"]) == (row["signature"], 2)


def test_t2514_stray_work_origin_already_holds_needs_nothing(world: Env) -> None:
    wt, run_dir, checkout = _repo(world, LINES, LINES.replace("a\n", "A\n").replace("g\n", "G\n"))
    _stray(checkout, {"lib.txt": LINES.replace("a\n", "A\n")})  # a session landed this edit and one more
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", _pull(checkout))
    assert done.passed
    assert "origin already holds them" in done.tail
    assert _filed() == []


def test_t2514_untracked_strays_count_as_landed_only_when_origin_has_the_same_file(world: Env) -> None:
    wt, _run_dir, checkout = _repo(world, "old\n", "new\n")
    (wt / "added.txt").write_text("same\n", encoding="utf-8")
    sh(wt, "git", "add", "added.txt")
    sh(wt, "git", "commit", "-qm", "add")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    sh(checkout, "git", "fetch", "-q", "origin")
    (checkout / "lib.txt").write_text("new\n", encoding="utf-8")  # the very content origin has
    (checkout / "added.txt").write_text("same\n", encoding="utf-8")
    assert stray.landed(checkout, "origin/main", _stash(checkout, "-u"))
    (checkout / "added.txt").write_text("his\n", encoding="utf-8")  # an untracked file origin has not
    assert not stray.landed(checkout, "origin/main", _stash(checkout, "-u"))
    (checkout / "lib.txt").write_text("new\n", encoding="utf-8")
    assert stray.landed(checkout, "origin/main", _stash(checkout))  # no untracked part at all
    (checkout / "CLAUDE.md").unlink()  # origin keeps it: a deletion origin lacks
    assert not stray.landed(checkout, "origin/main", _stash(checkout))


def _stash(checkout: Path, *flags: str) -> str:
    sh(checkout, "git", "stash", "push", "-q", *flags, "-m", "t")
    return sh(checkout, "git", "rev-parse", "stash@{0}").strip()


def test_t2514_a_stray_edit_that_conflicts_with_origin_goes_to_claude(world: Env) -> None:
    _wt, _run_dir, checkout = _repo(world, "old\n", "new\n")
    sh(checkout, "git", "fetch", "-q", "origin")
    (checkout / "lib.txt").write_text("other\n", encoding="utf-8")
    held = _stash(checkout)
    assert not stray.landed(checkout, "origin/main", held)
    assert not stray.landed(checkout, "origin/no-such-branch", held)  # git failed: route it, lose nothing


def test_t2514_a_stash_entry_gone_at_once_sets_nothing_aside(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wt, run_dir, checkout = _repo(world, "old\n", "new\n")
    _stray(checkout, {"lib.txt": "stray\n"})
    monkeypatch.setattr(deployheal, "_stash_of", lambda _checkout, _message: None)  # another session took it
    assert deployheal.set_aside(checkout, ["lib.txt"], run_dir / "deploy", CARD, time.time()) is None
    assert not (run_dir / "deploy").exists()
