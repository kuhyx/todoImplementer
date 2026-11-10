"""One run at a time per repo: the lock, the repo task waiting on it, older runs joining it (T1912)."""

from __future__ import annotations

import threading
import time

import pytest
from repofakes import IMPL, LIVE, PLAN, Rig
from todoimpl.board.state import RunState, save
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner import repolock
from todoimpl.runner.files import write_json
from todoimpl.runner.repolock import RepoLocks


def test_the_lock_has_one_holder_and_names_who_waits_on_whom() -> None:
    locks = RepoLocks()
    assert locks.acquire("kuhyx/Tutor", "aaaa1111-0") is None
    assert locks.acquire("kuhyx/tutor ", "bbbb2222-0") == "aaaa1111-0"  # the same repo, spelled differently
    assert locks.waits() == {"bbbb2222-0": "aaaa1111-0"}
    assert locks.acquire("kuhyx/tutor", "aaaa1111-0") is None  # the holder takes it again
    assert locks.free("kuhyx/tutor", "aaaa1111-0") is True
    assert locks.free("kuhyx/tutor", "bbbb2222-0") is False
    locks.release("aaaa1111-0")
    assert locks.waits() == {"bbbb2222-0": "aaaa1111-0"}
    assert locks.acquire("kuhyx/tutor", "bbbb2222-0") is None
    assert locks.waits() == {}
    assert locks.acquire("kuhyx/other", "cccc3333-0") is None  # another repo is free


def test_a_run_that_was_already_working_joins_without_waiting() -> None:
    locks = RepoLocks()
    assert locks.acquire("kuhyx/tutor", "aaaa1111-0") is None
    assert locks.acquire("kuhyx/tutor", "bbbb2222-0", force=True) is None
    assert locks.acquire("kuhyx/tutor", "cccc3333-0") in ("aaaa1111-0", "bbbb2222-0")
    locks.release("aaaa1111-0")
    locks.release("cccc3333-0")
    assert locks.free("kuhyx/tutor", "cccc3333-0") is False  # bbbb2222-0 still holds it
    locks.release("bbbb2222-0")
    assert locks.free("kuhyx/tutor", "cccc3333-0") is True


def test_wait_blocks_until_the_repo_is_free_or_the_caller_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repolock, "POLL", 0.01)
    locks = RepoLocks()
    locks.acquire("kuhyx/tutor", "aaaa1111-0")
    got: list[bool] = []
    waiter = threading.Thread(
        target=lambda: got.append(locks.wait("kuhyx/tutor", "bbbb2222-0", lambda: False))
    )
    waiter.start()
    time.sleep(0.1)
    assert got == []
    assert locks.waits() == {"bbbb2222-0": "aaaa1111-0"}
    locks.release("aaaa1111-0")
    waiter.join(5)
    assert got == [True]
    assert locks.wait("kuhyx/tutor", "cccc3333-0", lambda: True) is False  # gave up: no wait mark left
    assert locks.waits() == {}


def test_t1913_a_repo_task_waits_for_the_run_that_holds_its_repo_and_the_card_says_so(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\ndone_check: true")
    card = repo_card_id(repo)
    write_json(rig.run_dir(card) / files.DONE, {"done": [f"{note}-0"], "steps": {}})
    rig.script(card, PLAN, IMPL, LIVE)
    assert rig.sched.locks.acquire(repo, "2d0704cd-7") is None  # an umbrella child works on this repo
    rig.sched.start(card)
    rig.until(lambda: rig.sched.lock_waits() == {card: "2d0704cd-7"})
    time.sleep(0.3)
    shown = rig.card(repo)
    assert (shown["status"], shown["waits_on"]) == ("queued", "2d0704cd-7")
    assert card not in rig.sched.running()
    assert rig.world.calls() == []
    with rig.sched._cv:
        rig.sched.locks.release("2d0704cd-7")
        rig.sched._cv.notify_all()
    rig.wait(card, {"gate"})
    assert rig.sched.lock_waits() == {}
    assert rig.sched.locks.free(repo, "someone-else") is True  # the finished drive let go


def test_cancelling_a_waiting_repo_task_clears_its_wait(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "demo todos", "## alpha\nMake alpha.\ndone_check: true")
    card = repo_card_id(repo)
    rig.sched.locks.acquire(repo, "2d0704cd-7")
    rig.sched.start(card)
    rig.until(lambda: rig.sched.lock_waits() == {card: "2d0704cd-7"})
    rig.sched.cancel(card)
    assert rig.sched.lock_waits() == {}
    assert rig.state(card).stage == "cancelled"


def test_admission_lets_a_surviving_turn_in_and_makes_every_other_run_wait(rig: Rig) -> None:
    repo = rig.repo()
    repo_card = repo_card_id(repo)
    root = rig.world.root
    save(root / repo_card, RunState(task_id=repo_card, stage="plan", repo=repo, extra={"repotask": True}))
    save(root / "aaaa1111-0", RunState(task_id="aaaa1111-0", stage="implement", repo=repo))
    save(root / "bbbb2222-0", RunState(task_id="bbbb2222-0", stage="implement", repo=repo))
    save(root / "cccc3333-0", RunState(task_id="cccc3333-0", stage="implement", repo=repo))
    write_json(root / "cccc3333-0" / "turn.pid", {"stem": "implement-1", "role": "implement"})
    save(root / "nore0001-0", RunState(task_id="nore0001-0", stage="plan"))
    save(
        root / "umbr0001-0",
        RunState(task_id="umbr0001-0", stage="implement", repo=repo, note_body="Umbrella: per-repo\n"),
    )
    assert rig.sched._admit("nore0001-0") is True  # no repo: no lock
    assert rig.sched._admit("umbr0001-0") is True  # an umbrella's children take the locks, not the umbrella
    assert rig.sched._admit("gone0000-0") is True  # no state: nothing to lock
    assert rig.sched._admit(repo_card) is True  # the repo task takes the free repo
    assert rig.sched._admit("aaaa1111-0") is False  # kuhy's Retry on an older card waits for the repo task
    assert rig.sched.lock_waits() == {"aaaa1111-0": repo_card}
    assert (
        rig.sched._admit("cccc3333-0") is True
    )  # a turn that survived a restart is already working: it joins
    rig.sched.locks.release(repo_card)
    assert rig.sched._admit("aaaa1111-0") is False  # the surviving run still holds the repo
    rig.sched.locks.release("cccc3333-0")
    assert rig.sched._admit("aaaa1111-0") is True
    assert rig.sched._admit("bbbb2222-0") is False
    assert rig.sched.lock_waits() == {"bbbb2222-0": "aaaa1111-0"}
