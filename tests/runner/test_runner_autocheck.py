"""The auto-close poll: switch, baseline, trust, reasons and deferral under a limit."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from autofakes import Starts, arm, cache, poller, switch, trust, trust_file
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import autocheck
from todoimpl.runner.autocheck import (
    BASELINE,
    DEFERRED,
    NO_REPO,
    NOTE_LEVEL,
    RUN_EXISTS,
    STARTED,
    TIMED_OUT,
    UNTRUSTED,
    WAITING,
    check_hash,
    load_trusted,
)

# One real line of ~/.config/todo-hooks/trusted-checks and the note's done_check it was written for.
REAL_LINE = "31335b8bfcbeace5901d12e2e69173149d1a8ac289a53ec8a455767b502fa386  # aa36f61e kuhyx/herosi"
REAL_CHECK = "test -f ~/.config/herosi/improvements_confirmed"


def _setup(world: Env, **fields: object) -> tuple[FakeClient, Path, str]:
    make_repo(world)
    marker = world.tmp / "marker"
    check = f"test -e {marker}"
    client = FakeClient({"abcd1234": task(done_check=check, **fields)})  # type: ignore[arg-type]
    return client, marker, check


def test_the_preimage_matches_todo_hooks_on_a_real_trust_line(tmp_path: Path) -> None:
    path = tmp_path / "trusted-checks"
    path.write_text(f"# header\n{REAL_LINE}\n", encoding="utf-8")
    assert load_trusted(path) == {REAL_LINE.split(maxsplit=1)[0]}
    assert check_hash(f"  {REAL_CHECK}\n") == REAL_LINE.split(maxsplit=1)[0]
    assert load_trusted(tmp_path / "missing") == set()
    (tmp_path / "bad").write_bytes(b"\xff\xfe")
    assert load_trusted(tmp_path / "bad") == set()


def test_trust_file_honours_the_todo_hooks_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TODO_HOOKS_TRUST_FILE", str(tmp_path / "t"))
    assert autocheck.trust_file() == tmp_path / "t"


def test_switch_off_runs_nothing_and_drops_the_cache(world: Env) -> None:
    client, marker, check = _setup(world)
    arm(world, check)
    marker.touch()
    starts = Starts()
    for value in (None, False):
        switch(world, on=value)
        (world.root / "autocheck.json").write_text("{}", encoding="utf-8")
        poller(world, starts, client).tick()
        assert not (world.root / "autocheck.json").exists()
    (world.root / "settings.json").write_text("[1]", encoding="utf-8")
    assert not autocheck.enabled(world.root)
    assert starts.calls == []


def test_baseline_skips_what_already_passes_until_it_goes_red_and_green_again(world: Env) -> None:
    client, marker, check = _setup(world)
    trust(world, check)
    switch(world, on=True)
    marker.touch()
    starts = Starts()
    auto = poller(world, starts, client)
    auto.tick()
    assert cache(world)[CARD]["reason"] == BASELINE
    auto.tick()
    assert cache(world)[CARD]["reason"] == BASELINE
    marker.unlink()
    auto.tick()
    assert cache(world)[CARD] | {"at": 0} == {
        "at": 0,
        "passed": False,
        "trusted": True,
        "reason": WAITING,
        "pending": False,
    }
    marker.touch()
    auto.tick()
    assert (starts.calls, cache(world)[CARD]["reason"]) == ([CARD], STARTED)


def test_unseen_item_that_passes_after_the_baseline_starts(world: Env) -> None:
    client, marker, check = _setup(world)
    arm(world, check)
    marker.touch()
    starts = Starts(result=False)
    poller(world, starts, client).tick()
    assert (starts.calls, cache(world)[CARD]["reason"]) == ([CARD], RUN_EXISTS)


def test_untrusted_and_removed_trust_lines_never_run(world: Env) -> None:
    client, marker, _check = _setup(world)
    arm(world, "something else")
    marker.touch()
    starts = Starts()
    auto = poller(world, starts, client)
    auto.tick()
    assert cache(world)[CARD] | {"at": 0} == {
        "at": 0,
        "passed": False,
        "trusted": False,
        "reason": UNTRUSTED,
        "pending": False,
    }
    trust_file(world).unlink()
    auto.tick()
    assert cache(world)[CARD]["reason"] == UNTRUSTED
    assert starts.calls == []


def test_note_level_check_of_a_multi_item_note_is_ignored_but_an_own_check_is_polled(world: Env) -> None:
    client, _marker, check = _setup(world, body="## One\ntext\n## Two\ndone_check: `test -e /nonexistent`\n")
    arm(world, check, "test -e /nonexistent")
    poller(world, Starts(), client).tick()
    got = cache(world)
    assert (got["abcd1234-0"]["reason"], got["abcd1234-0"]["trusted"]) == (NOTE_LEVEL, True)
    assert got["abcd1234-1"]["reason"] == WAITING


def test_no_repo_checkout_is_not_polled(world: Env) -> None:
    client = FakeClient(
        {"abcd1234": task(done_check="true"), "ffff0000": task("ffff0000", repo=None, done_check="true")}
    )
    arm(world, "true")
    starts = Starts()
    poller(world, starts, client).tick()
    assert {k: v["reason"] for k, v in cache(world).items()} == {"abcd1234-0": NO_REPO, "ffff0000-0": NO_REPO}
    assert starts.calls == []


def test_a_slow_check_times_out_counts_red_and_others_still_run(world: Env) -> None:
    client, marker, check = _setup(world)
    client.tasks["bbbb0000"] = task("bbbb0000", done_check="sleep 5")
    arm(world, check, "sleep 5")
    marker.touch()
    starts = Starts()
    poller(world, starts, client, timeout=0.3).tick()
    assert cache(world)["bbbb0000-0"]["reason"] == TIMED_OUT
    assert starts.calls == [CARD]


def test_a_check_that_cannot_start_counts_red(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _marker, check = _setup(world)
    arm(world, check)
    monkeypatch.setenv("TODOIMPL_CAPPED", str(world.tmp / "no-such-capped"))
    poller(world, Starts(), client).tick()
    assert cache(world)[CARD]["reason"] == WAITING


def test_a_pass_under_a_usage_limit_is_deferred_not_dropped(world: Env) -> None:
    client, marker, check = _setup(world)
    arm(world, check)
    marker.touch()
    (world.root / "limit-until").write_text(str(time.time() + 3600), encoding="utf-8")
    starts = Starts()
    auto = poller(world, starts, client)
    auto.tick()
    assert (cache(world)[CARD]["reason"], cache(world)[CARD]["pending"], starts.calls) == (DEFERRED, True, [])
    (world.root / "limit-until").unlink()
    auto.tick()
    assert (cache(world)[CARD]["reason"], starts.calls) == (STARTED, [CARD])


def test_runs_that_exist_are_never_started_and_keep_their_entry(world: Env) -> None:
    client, marker, check = _setup(world)
    client.tasks["cccc0000"] = task("cccc0000", done_check=check)
    client.tasks["dddd0000"] = task("dddd0000", done_check=check)
    arm(world, check)
    marker.touch()
    store.save(world.root / CARD, RunState(task_id=CARD, stage="implement"))
    failed = RunState(
        task_id="cccc0000-0", stage="failed", auto_start={"reason": "done_check", "passed_at": 1}
    )
    store.save(world.root / "cccc0000-0", failed)
    (world.root / "dddd0000-0").mkdir()
    (world.root / "dddd0000-0" / "state.json").write_text("{", encoding="utf-8")
    starts = Starts()
    poller(world, starts, client).tick()
    got = cache(world)
    assert CARD not in got
    assert "dddd0000-0" not in got
    assert got["cccc0000-0"]["reason"] == RUN_EXISTS
    assert starts.calls == []


def test_closed_items_and_items_without_a_check_are_skipped(world: Env) -> None:
    client = FakeClient({"abcd1234": task(done_check=None), "eeee0000": task("eeee0000", done_check="true")})
    client.tasks["eeee0000"] = client.tasks["eeee0000"].__class__(
        "eeee0000", "t", "", "kuhyx/demo", "done", "medium", "true"
    )
    arm(world, "true")
    poller(world, Starts(), client).tick()
    assert cache(world) == {}
