"""The limit probe lifts a stored plan limit the real usage no longer backs (early resets happen)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from todoimpl.credits import marks
from todoimpl.runner import limits
from todoimpl.runner.limitprobe import LimitProbe
from todoimpl.usage import oauth
from todoimpl.usage.limits import limit_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NOW = 1_794_320_000.0
FRIDAY = NOW + 2.75 * 86400


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


def _usable(now: float) -> oauth.Probe:
    return oauth.Probe(now, None, oauth.Window(0.03, FRIDAY))


def _make(root: Path, fetch: Callable[[float], oauth.Probe | None], clock: Clock, **kw: float) -> LimitProbe:
    return LimitProbe(root, fetch=fetch, clock=clock, **kw)


def test_t1882_a_stored_limit_is_lifted_when_the_plan_is_usable(tmp_path: Path) -> None:
    """Both 7 d and 5 h were reset early, yet limit-until (Fri 10:00) paused every run."""
    clock = Clock()
    limits.write_until(tmp_path, FRIDAY)
    marks.mark_exhausted(tmp_path, FRIDAY, "Credit balance is too low")
    probe = _make(tmp_path, _usable, clock)
    assert probe.tick() == _usable(NOW)
    assert not limit_state(tmp_path).active(NOW)
    assert not marks.exhausted(tmp_path, NOW)
    assert oauth.load(tmp_path) == _usable(NOW)


def test_a_limit_the_plan_still_reports_moves_to_the_real_reset(tmp_path: Path) -> None:
    clock = Clock()
    limits.write_until(tmp_path, FRIDAY)
    full = oauth.Probe(NOW, None, oauth.Window(1.0, NOW + 7200))
    _make(tmp_path, lambda _now: full, clock).tick()
    assert limit_state(tmp_path).until == NOW + 7200
    marks.mark_exhausted(tmp_path, NOW + 7200, "x")
    _make(tmp_path, lambda _now: full, clock).tick()
    assert marks.exhausted(tmp_path, NOW)


def test_an_unknown_probe_changes_nothing(tmp_path: Path) -> None:
    limits.write_until(tmp_path, FRIDAY)
    assert _make(tmp_path, lambda _now: None, Clock()).tick() is None
    assert limit_state(tmp_path).until == FRIDAY
    assert oauth.load(tmp_path) is None


def test_without_a_limit_the_probe_only_records(tmp_path: Path) -> None:
    assert _make(tmp_path, _usable, Clock()).tick() is not None
    assert limit_state(tmp_path).until is None
    assert oauth.load(tmp_path) is not None


def test_refresh_if_due_probes_in_the_background_only_while_limited_and_not_too_often(tmp_path: Path) -> None:
    clock, calls, done = Clock(), [], threading.Event()

    def fetch(now: float) -> oauth.Probe:
        calls.append(now)
        done.set()
        return _usable(now)

    probe = _make(tmp_path, fetch, clock, min_gap=60.0)
    probe.refresh_if_due()  # no limit: nothing to lift
    assert calls == []
    limits.write_until(tmp_path, FRIDAY)
    probe.refresh_if_due()
    assert done.wait(5)
    probe.join()
    assert len(calls) == 1
    limits.write_until(tmp_path, FRIDAY)
    probe.refresh_if_due()  # just probed
    probe.join()
    assert len(calls) == 1
    clock.now += 61
    probe.refresh_if_due()
    probe.join()
    assert len(calls) == 2


def test_the_loop_probes_at_start_and_stops(tmp_path: Path) -> None:
    seen = threading.Event()

    def fetch(now: float) -> oauth.Probe:
        seen.set()
        return _usable(now)

    limits.write_until(tmp_path, FRIDAY)
    probe = _make(tmp_path, fetch, Clock(), interval=0.05)
    probe.start()
    probe.start()  # idempotent
    assert seen.wait(5)
    probe.stop()
    probe.stop()
    assert not limit_state(tmp_path).active(NOW)


def test_a_crashing_fetch_never_kills_the_loop(tmp_path: Path) -> None:
    hits = threading.Event()
    n = [0]

    def fetch(now: float) -> oauth.Probe:
        n[0] += 1
        if n[0] == 1:
            raise RuntimeError("boom")
        hits.set()
        return _usable(now)

    probe = _make(tmp_path, fetch, Clock(), interval=0.05)
    probe.start()
    assert hits.wait(5)
    probe.stop()


def test_join_and_stop_before_anything_started_are_noops(tmp_path: Path) -> None:
    probe = _make(tmp_path, _usable, Clock())
    probe.join()
    probe.stop()
