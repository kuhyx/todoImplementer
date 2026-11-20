"""T2377: a run whose `kuhyx/<name>` repo is not on GitHub creates it, then clones it (draft-studio)."""

from pathlib import Path

import pytest
from runnerfakes import Env
from todoimpl.board import clone
from todoimpl.board.state import RunState
from todoimpl.runner import worktree
from todoimpl.runner.files import NeedsYouError

MISSING = "GraphQL: Could not resolve to a Repository with the name 'kuhyx/{name}'. (repository)"
# A stub gh: `repo create` records the repo as made; `repo clone` of an unmade repo says gh's NOT_FOUND line;
# a made one becomes a git repo with one commit on main and origin/main (what --add-readme gives).
GH = """#!/bin/sh
echo "$@" >> "$GH_LOG"
if [ "$1 $2" = "repo create" ]; then touch "$GH_MADE/$(basename "$3")"; exit 0; fi
if [ "$1 $2" = "repo clone" ]; then
  name=$(basename "$3")
  [ "$name" = offline ] && { echo "error connecting to api.github.com" >&2; exit 1; }
  [ -e "$GH_MADE/$name" ] || { printf '%s\\n' "$MISSING" | sed "s/{name}/$name/" >&2; exit 1; }
  git init -q -b main "$4" && git -C "$4" commit -q --allow-empty -m readme \
    && git -C "$4" remote add origin "https://github.com/$3" \
    && git -C "$4" update-ref refs/remotes/origin/main HEAD
  exit 0
fi
exit 2
"""


@pytest.fixture
def gh(world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shim = tmp_path / "ghbin" / "gh"
    shim.parent.mkdir()
    shim.write_text(GH, encoding="utf-8")
    shim.chmod(0o755)
    (tmp_path / "made").mkdir()
    monkeypatch.setattr(clone, "GH", str(shim))
    monkeypatch.setenv("GH_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("GH_MADE", str(tmp_path / "made"))
    monkeypatch.setenv("MISSING", MISSING)
    return tmp_path / "log"


def calls(log: Path) -> list[list[str]]:
    return [line.split() for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def test_t2377_a_missing_kuhyx_repo_is_created_public_then_cloned(world: Env, gh: Path) -> None:
    path = worktree.repo_dir("kuhyx/draft-studio", clone=True, public=True)
    assert path == world.src / "draft-studio"
    made = calls(gh)
    assert made[1][:3] == ["repo", "create", "kuhyx/draft-studio"]
    assert "--public" in made[1]
    assert "--add-readme" in made[1]
    assert made[2][:3] == ["repo", "clone", "kuhyx/draft-studio"]
    assert worktree.base_ref(path) == ("origin/main", "main")


def test_t2377_private_unless_the_note_says_public(world: Env, gh: Path) -> None:
    worktree.repo_dir("kuhyx/quiet", clone=True)
    create = next(c for c in calls(gh) if c[:2] == ["repo", "create"])
    assert "--private" in create
    assert "--public" not in create


def test_t2377_another_owners_missing_repo_still_fails(world: Env, gh: Path) -> None:
    with pytest.raises(NeedsYouError, match="Could not resolve to a Repository"):
        worktree.repo_dir("someone/ghost", clone=True, public=True)
    assert not any(c[:2] == ["repo", "create"] for c in calls(gh))


def test_t2377_a_network_failure_creates_nothing(world: Env, gh: Path) -> None:
    with pytest.raises(NeedsYouError, match="error connecting") as err:
        worktree.repo_dir("kuhyx/offline", clone=True, public=True)
    assert err.value.kind == "run_failed"
    assert not any(c[:2] == ["repo", "create"] for c in calls(gh))


@pytest.mark.parametrize(
    ("body", "public"),
    [
        ("what\nvisibility: public\n", True),
        ("  Visibility:  PUBLIC  ", True),
        ("visibility: private", False),
        ("visibility: public\nvisibility: private", False),  # a contradiction stays private
        ("a new public repo", False),  # prose is not the line
        ("```\nvisibility: public\n```", False),  # an example in a fence is not the note's choice
        ("", False),
    ],
)
def test_t2377_visibility_line(body: str, public: bool) -> None:
    assert clone.wants_public(body) is public


def test_t2377_attach_reads_the_visibility_from_the_body(world: Env, gh: Path) -> None:
    st = RunState(task_id="389b5a10-0", stage="spec")
    worktree.attach(st, "kuhyx/draft-studio", world.root, body="## Draft studio\nvisibility: public\n")
    assert "--public" in next(c for c in calls(gh) if c[:2] == ["repo", "create"])
    assert Path(str(st.worktree)).is_dir()


def test_t2377_an_existing_dir_of_another_origin_creates_nothing(world: Env, gh: Path) -> None:
    (world.src / "cleanup-plate").mkdir(parents=True)  # T2272: ~/src/<name> whose origin is someone else's
    with pytest.raises(NeedsYouError, match="Could not resolve to a Repository"):
        worktree.repo_dir("kuhyx/cleanup-plate", clone=True)
    assert not any(c[:2] == ["repo", "create"] for c in calls(gh))
