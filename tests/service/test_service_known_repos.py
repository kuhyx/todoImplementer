"""T2413: a GitHub repo with no notes yet is on the board repo list and in the new-task picker."""

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from contract_lib import validate
from servicefakes import FakeScheduler, Rig
from todoimpl.service import build_backend
from todoimpl.service.known_repos import RETRY_S, TTL_S, KnownRepos
from todoimpl.todo_mcp.client import TodoClient


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def inline(job: Callable[[], None]) -> None:
    job()


def test_t2413_board_lists_github_repos_that_have_no_notes(rig: Rig) -> None:
    rig.note(repo="kuhyx/demo")
    rig.backend.known_repos = lambda: ["kuhyx/demo", "kuhyx/logo-review"]
    board = rig.backend.board()
    validate("board", board)
    assert board["repos"] == ["kuhyx/demo", "kuhyx/logo-review"]


def test_board_without_a_repo_source_lists_only_card_repos(rig: Rig) -> None:
    rig.note(repo="kuhyx/demo")
    assert rig.backend.board()["repos"] == ["kuhyx/demo"]


def test_a_first_get_answers_at_once_and_the_fetch_lands_after() -> None:
    jobs: list[Callable[[], None]] = []
    known = KnownRepos(lambda: ["kuhyx/a"], spawn=jobs.append, clock=Clock())
    assert known.get() == []  # never blocks on gh
    assert known.get() == []  # one refresh in flight, not two
    assert len(jobs) == 1
    jobs[0]()
    assert known.get() == ["kuhyx/a"]


def test_a_new_repo_shows_up_after_the_ttl() -> None:
    clock, names = Clock(), [["kuhyx/a"], ["kuhyx/a", "kuhyx/new"]]
    known = KnownRepos(lambda: names.pop(0), spawn=inline, clock=clock)
    assert known.get() == ["kuhyx/a"]
    clock.now += TTL_S - 1
    assert known.get() == ["kuhyx/a"]  # still fresh
    clock.now += 2
    assert known.get() == ["kuhyx/a", "kuhyx/new"]  # stale: refreshed, the new repo is in


def test_a_failed_fetch_keeps_the_old_list_and_retries_soon() -> None:
    clock = Clock()
    results: list[list[str] | OSError] = [["kuhyx/a"], OSError("gh down"), ["kuhyx/a", "kuhyx/b"]]

    def fetch() -> list[str]:
        result = results.pop(0)
        if isinstance(result, OSError):
            raise result
        return result

    known = KnownRepos(fetch, spawn=inline, clock=clock)
    assert known.get() == ["kuhyx/a"]
    clock.now += TTL_S + 1
    assert known.get() == ["kuhyx/a"]  # the refresh fails: the old list stays
    clock.now += RETRY_S - 1
    assert known.get() == ["kuhyx/a"]  # no gh call before the retry delay
    clock.now += 2
    assert known.get() == ["kuhyx/a", "kuhyx/b"]


def test_the_default_source_is_gh_and_a_built_backend_wires_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("todoimpl.service.known_repos.gh_repos", lambda: ["kuhyx/logo-review"])
    client = TodoClient("http://127.0.0.1:1/mcp", "t")
    backend = build_backend(root=tmp_path, build="x", client=client, scheduler=FakeScheduler())
    try:
        deadline = time.monotonic() + 5
        while "kuhyx/logo-review" not in backend.known_repos() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "kuhyx/logo-review" in backend.known_repos()
    finally:
        backend.cache.stop()
