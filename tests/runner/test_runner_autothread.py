"""The auto-close poll's cache across restarts and its background thread."""

from __future__ import annotations

from pathlib import Path

from autofakes import Starts, arm, cache, poller
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, wait
from todoimpl.runner import autocheck
from todoimpl.runner.autocheck import WAITING, load_cache


def _setup(world: Env) -> tuple[FakeClient, Path, str]:
    make_repo(world)
    marker = world.tmp / "marker"
    check = f"test -e {marker}"
    return FakeClient({"abcd1234": task(done_check=check)}), marker, check


def test_cache_survives_a_restart_and_bad_files_read_as_empty(world: Env) -> None:
    client, marker, check = _setup(world)
    arm(world, check)
    poller(world, Starts(), client).tick()
    assert load_cache(world.root)[CARD]["reason"] == WAITING
    marker.touch()
    starts = Starts()
    poller(world, starts, client).tick()
    assert starts.calls == [CARD]
    (world.root / "autocheck.json").write_text('{"x": 1, "y": {"passed": true}}', encoding="utf-8")
    assert load_cache(world.root) == {"y": {"passed": True}}
    (world.root / "autocheck.json").write_text("[]", encoding="utf-8")
    assert load_cache(world.root) == {}


def test_thread_ticks_at_once_survives_a_crash_and_stops(world: Env) -> None:
    client, marker, check = _setup(world)
    arm(world, check)
    marker.touch()
    starts = Starts()
    seen: list[int] = []

    def cards() -> list[object]:
        seen.append(1)
        if len(seen) == 1:
            msg = "boom"
            raise RuntimeError(msg)
        return [client.get_task(CARD)]

    auto = autocheck.AutoCloser(world.root, cards, starts, interval=0.05)  # type: ignore[arg-type]
    auto.start()
    auto.start()
    try:
        wait(lambda: starts.calls == [CARD])
    finally:
        auto.stop()
    assert auto._thread is not None
    assert not auto._thread.is_alive()
    autocheck.AutoCloser(world.root, cards, starts).stop()  # type: ignore[arg-type]


def test_a_stop_mid_tick_skips_the_rest(world: Env) -> None:
    client, _marker, check = _setup(world)
    arm(world, check)
    auto = poller(world, Starts(), client)
    auto._stop.set()
    auto.tick()
    assert cache(world) == {}


def test_note_red_needs_the_switch_and_a_newer_entry_survives_the_ticks_rewrite(world: Env) -> None:
    autocheck.note_red(world.root, CARD, 5.0)
    assert not (world.root / "autocheck.json").exists()
    client, marker, check = _setup(world)
    arm(world, check)
    marker.touch()
    auto = poller(world, Starts(), client)

    def cards() -> list[object]:
        autocheck.note_red(world.root, CARD, 10.0**12)  # a red Close lands while the tick runs
        return [client.get_task(CARD)]

    auto.cards = cards  # type: ignore[assignment]
    auto.tick()
    assert cache(world)[CARD] == {
        "at": 10.0**12,
        "passed": False,
        "trusted": True,
        "reason": WAITING,
        "pending": False,
    }
