"""The start gate: weekly usage under 80 %, free credits, free gateway; fail closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.errors.gate import Gate
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_000_000.0


def probe(used: float | None, at: float = NOW) -> oauth.Probe:
    week = None if used is None else oauth.Window(used, NOW + 86400)
    return oauth.Probe(at, None, week)


def gate(tmp: Path, *, fetched: oauth.Probe | None = None, credit: bool = False, free: bool = False) -> Gate:
    calls: list[float] = []

    def fetch(now: float) -> oauth.Probe | None:
        calls.append(now)
        return fetched

    made = Gate(fetch=fetch, credits=lambda _root, _now: credit, free=lambda _repo: free)
    made.calls = calls  # type: ignore[attr-defined]
    return made


def calls(g: Gate) -> list[float]:
    return g.calls  # type: ignore[attr-defined, no-any-return]


def test_under_eighty_percent_this_week_opens_the_gate(tmp_path: Path) -> None:
    g = gate(tmp_path, fetched=probe(0.79))
    assert g.check(tmp_path, "kuhyx/kartka", NOW) == "weekly"
    assert calls(g) == [NOW]  # no stored probe: read it right now
    assert oauth.load(tmp_path) == probe(0.79)  # and keep it for the board


def test_eighty_percent_or_more_keeps_it_shut(tmp_path: Path) -> None:
    assert gate(tmp_path, fetched=probe(0.80)).check(tmp_path, "kuhyx/kartka", NOW) is None
    assert gate(tmp_path, fetched=probe(1.0)).check(tmp_path, "kuhyx/kartka", NOW) is None


def test_an_unknown_usage_fails_closed(tmp_path: Path) -> None:
    assert gate(tmp_path, fetched=None).check(tmp_path, "kuhyx/kartka", NOW) is None
    assert gate(tmp_path, fetched=probe(None)).check(tmp_path, "kuhyx/kartka", NOW) is None


def test_a_fresh_stored_probe_is_used_but_a_stale_one_is_read_again(tmp_path: Path) -> None:
    oauth.save(tmp_path, probe(0.1, at=NOW - 10))
    fresh = gate(tmp_path, fetched=probe(0.95))
    assert fresh.check(tmp_path, "kuhyx/kartka", NOW) == "weekly"
    assert calls(fresh) == []
    oauth.save(tmp_path, probe(0.1, at=NOW - 10_000))
    stale = gate(tmp_path, fetched=probe(0.95))
    assert stale.check(tmp_path, "kuhyx/kartka", NOW) is None
    assert calls(stale) == [NOW]


def test_free_credits_open_the_gate_over_the_weekly_limit(tmp_path: Path) -> None:
    assert gate(tmp_path, fetched=probe(0.9), credit=True).check(tmp_path, "kuhyx/kartka", NOW) == "credits"


def test_a_public_repo_with_a_live_free_gateway_opens_it_last(tmp_path: Path) -> None:
    g = gate(tmp_path, fetched=probe(0.9), free=True)
    assert g.check(tmp_path, "kuhyx/kartka", NOW) == "free"
    assert (
        gate(tmp_path, fetched=probe(0.9), credit=True, free=True).check(tmp_path, "kuhyx/kartka", NOW)
        == "credits"
    )


def test_the_real_probes_answer_no_without_a_plan_login_or_a_clone(tmp_path: Path) -> None:
    real = Gate()
    assert real.credits(tmp_path, NOW) is False  # the conftest turns the fallback off
    assert real.free("kuhyx/not-cloned-anywhere") is False
