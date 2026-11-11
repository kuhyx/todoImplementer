"""The credit ledger: per-turn cost deltas of cumulative session totals, durable, rebuilt once."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from todoimpl.credits import ledger

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _fresh_books() -> None:
    ledger.reset()


def write_turn(
    run: Path, stem: str, *, route: str | None, session: str, cost: float | None, ended: float
) -> None:
    """Write a stream (plus route and exit files) as the turn host leaves it; cost None: killed."""
    run.mkdir(parents=True, exist_ok=True)
    lines: list[dict[str, Any]] = [{"type": "system", "subtype": "init", "session_id": session}]
    if cost is not None:
        lines.append({"type": "result", "session_id": session, "total_cost_usd": cost, "num_turns": 1})
    junk = ['{"type": "result", broken\n', json.dumps({"type": "user", "kind": "result"}) + "\n"]
    body = "".join(json.dumps(x) + "\n" for x in lines) + "".join(junk) + "{torn"
    (run / f"{stem}.stream.jsonl").write_text(body)
    if route is not None:
        (run / f"{stem}.route").write_text(route)
    (run / f"{stem}.exit.json").write_text(json.dumps({"code": 0, "ended": ended}))


def test_delta_charges_what_a_resumed_turn_added() -> None:
    seen: dict[str, float] = {}
    assert ledger.delta(seen, "s", 1.0) == 1.0
    assert ledger.delta(seen, "s", 3.0) == 2.0
    assert ledger.delta(seen, "s", 0.5) == 0.5  # the counter restarted: the whole total is the cost
    assert ledger.delta(seen, "s", 0.0) == 0.0
    assert ledger.delta(seen, "s", None) == 0.0
    assert ledger.delta(seen, None, 0.7) == 0.7
    assert seen == {"s": 0.5}


def test_backfill_sums_session_deltas_not_cumulative_totals(tmp_path: Path) -> None:
    run = tmp_path / "abcd1234-0"
    write_turn(run, "plan-1000.000", route=None, session="s1", cost=1.0, ended=1001.0)
    write_turn(run, "implement-1002.000", route="credits", session="s1", cost=3.0, ended=1003.0)
    write_turn(run, "implement-1004.000", route="credits", session="s1", cost=None, ended=1005.0)  # killed
    write_turn(run, "implement-1006.000", route="credits", session="s1", cost=3.5, ended=1007.0)
    write_turn(run, "review-1008.000", route="credits", session="s2", cost=2.0, ended=1009.0)
    child = tmp_path / "umb00000-0" / "children" / "child001-0"
    write_turn(child, "implement-1010.000", route="credits", session="s3", cost=1.5, ended=1011.0)

    assert ledger.load(tmp_path) == 6
    assert ledger.spent(tmp_path, 0.0) == pytest.approx(2.0 + 0.5 + 2.0 + 1.5)
    assert ledger.turns(tmp_path, 0.0) == 5  # the killed turn counts, at cost 0
    assert ledger.spent(tmp_path, 0.0, route="plan") == 1.0
    assert ledger.spent(tmp_path, 1006.0) == pytest.approx(0.5 + 2.0 + 1.5)  # ended_at >= since
    assert ledger.turns(tmp_path, 1006.0) == 3
    assert (tmp_path / ledger.LEDGER_FILE).exists()


def test_a_second_start_reads_the_file_and_does_not_scan_streams_again(tmp_path: Path) -> None:
    run = tmp_path / "abcd1234-0"
    write_turn(run, "implement-1002.000", route="credits", session="s1", cost=3.0, ended=1003.0)
    assert ledger.load(tmp_path) == 1
    (run / "implement-1002.000.stream.jsonl").unlink()
    ledger.reset()
    assert ledger.load(tmp_path) == 1
    assert ledger.spent(tmp_path, 0.0) == 3.0


def test_no_streams_and_no_ledger_means_no_ledger_file(tmp_path: Path) -> None:
    assert ledger.load(tmp_path) == 0
    assert ledger.spent(tmp_path, 0.0) == 0.0
    assert not (tmp_path / ledger.LEDGER_FILE).exists()


def test_record_appends_the_delta_against_the_loaded_session_totals(tmp_path: Path) -> None:
    run = tmp_path / "abcd1234-0"
    write_turn(run, "plan-1000.000", route=None, session="s1", cost=1.0, ended=1001.0)
    ledger.load(tmp_path)
    paid = ledger.record(
        tmp_path, task="abcd1234-0", stem="implement-2000.000", role="implement", route="credits",
        session_id="s1", cumulative=4.0, ended_at=2001.0,
    )  # fmt: skip
    assert paid == 3.0
    killed = ledger.record(
        tmp_path, task="abcd1234-0", stem="implement-2002.000", role="implement", route="credits",
        session_id="s1", cumulative=None, ended_at=2003.0,
    )  # fmt: skip
    assert killed == 0.0
    ledger.reset()
    ledger.load(tmp_path)
    assert ledger.spent(tmp_path, 0.0) == 3.0
    assert ledger.turns(tmp_path, 0.0) == 2
    last = json.loads((tmp_path / ledger.LEDGER_FILE).read_text().splitlines()[-1])
    assert last == {
        "stem": "implement-2002.000", "task": "abcd1234-0", "role": "implement", "route": "credits",
        "session_id": "s1", "cumulative_usd": None, "delta_usd": 0.0, "ended_at": 2003.0,
    }  # fmt: skip


def test_a_stem_written_twice_counts_once_the_later_record_wins(tmp_path: Path) -> None:
    line = {
        "stem": "implement-1.000", "task": "t", "role": "implement", "route": "credits", "session_id": "s",
        "cumulative_usd": None, "delta_usd": 0.0, "ended_at": 5.0,
    }  # fmt: skip
    later = {**line, "cumulative_usd": 2.0, "delta_usd": 2.0, "ended_at": 6.0}
    other = {**line, "stem": "implement-2.000", "route": "bogus"}
    text = "\n".join(
        [json.dumps(line), "{torn", json.dumps(later), "[1]", json.dumps(other), '{"stem": 3}', ""]
    )
    (tmp_path / ledger.LEDGER_FILE).write_text(text)
    assert ledger.load(tmp_path) == 1  # the bogus route and the stem-less lines are skipped
    assert ledger.spent(tmp_path, 0.0) == 2.0
    assert ledger.turns(tmp_path, 0.0) == 1


def test_recording_a_turn_the_backfill_already_saw_adds_nothing(tmp_path: Path) -> None:
    run = tmp_path / "abcd1234-0"
    write_turn(run, "implement-1002.000", route="credits", session="s1", cost=3.0, ended=1003.0)
    paid = ledger.record(
        tmp_path, task="abcd1234-0", stem="implement-1002.000", role="implement", route="credits",
        session_id="s1", cumulative=3.0, ended_at=1003.0,
    )  # fmt: skip
    assert paid == 3.0
    assert len((tmp_path / ledger.LEDGER_FILE).read_text().splitlines()) == 1
