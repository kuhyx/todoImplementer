"""After a Ship: resolve at the source, the fixed build, and when a fixed error reopens."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from errfakes import kartka_entry, shim
from loopfakes import CARD, KEY, World
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.errors import ledger
from todoimpl.runner.files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path


def test_t2017_a_shipped_error_is_resolved_at_its_source_with_the_fixed_build(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    ledger.mark_shipped(world.rig.root, [KEY], "abc123", 2_000_000_000.0)
    world.tick()
    assert world.hook_log.read_text(encoding="utf-8").strip() == "resolve 02b0d43d9f"
    entry = world.ledger()[KEY]
    assert (entry["state"], entry["fixed_build"], entry["installed_at"]) == ("fixed", 88, 2_000_000_000.0)


def test_t2017_a_failing_resolve_hook_is_tried_again_next_tick(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    ledger.mark_shipped(world.rig.root, [KEY], "abc123", 2_000_000_000.0)
    shim(world.tmp / "run.sh", world.hook_log, code=1)
    world.tick()
    assert world.ledger()[KEY]["state"] == "shipped"
    shim(world.tmp / "run.sh", world.hook_log)
    world.tick()
    assert world.ledger()[KEY]["state"] == "fixed"


def test_a_shipped_error_whose_source_is_gone_is_fixed_with_an_unknown_build(world: World) -> None:
    ledger.put(world.rig.root, "old:abc", state="shipped", repo="kuhyx/old", title="t", count=1, starts=1,
               commit="c", shipped_at=7.0)  # fmt: skip
    world.tick()
    entry = world.ledger()["old:abc"]
    assert (entry["state"], entry["fixed_build"]) == ("fixed", 0)


def fixed(world: World, **fields: Any) -> None:
    """Put a fixed entry for KEY in the ledger: shipped, resolved, installed at t=500."""
    base = {"state": "fixed", "repo": "kuhyx/kartka", "title": "Fix kartka: x", "count": 2, "starts": 1,
            "fixed_build": 50, "installed_at": 500.0}  # fmt: skip
    ledger.put(world.rig.root, KEY, **{**base, **fields})


def test_t2018_a_report_from_an_older_build_does_not_reopen_a_fixed_error(world: World) -> None:
    fixed(world)
    world.entries(kartka_entry(sample={"error": "x", "build": 49}))
    world.tick()
    assert world.tools("add_task") == []
    assert world.ledger()[KEY]["state"] == "fixed"


def test_t2018_a_report_from_the_fixed_build_or_newer_reopens_it(world: World) -> None:
    fixed(world)
    world.entries(kartka_entry(sample={"error": "x", "build": 50}))
    world.tick()
    (added,) = world.tools("add_task")
    assert "Regression: seen again on build 50; the fix shipped in build 50." in added["body"]
    assert world.ledger()[KEY]["state"] == "ticket"
    assert len(world.starts()) == 1  # the gate applies as for any new error


def test_t2019_with_no_build_a_report_after_the_install_reopens_and_one_before_does_not(world: World) -> None:
    fixed(world, fixed_build=0, installed_at=1_800_000_000.0)  # 2027-01-15
    world.entries(kartka_entry(last="2026-11-02T10:00:00Z"))
    world.tick()
    assert world.tools("add_task") == []  # the phone sent an old event late
    world.entries(kartka_entry(last="2027-02-01T00:00:00Z"))
    world.tick()
    assert len(world.tools("add_task")) == 1


def test_a_fixed_entry_with_no_install_time_or_a_bad_date_stays_closed(world: World) -> None:
    ledger.put(
        world.rig.root, KEY, state="fixed", repo="kuhyx/kartka", title="t", count=1, starts=1, fixed_build=0
    )
    world.entries(kartka_entry(last="2027-02-01T00:00:00Z"))
    world.tick()
    fixed(world, fixed_build=0)
    world.entries(kartka_entry(last="not a date"))
    world.tick()
    assert world.tools("add_task") == []


def test_a_shipped_entry_waits_for_its_resolve_before_anything_else(world: World) -> None:
    ledger.put(world.rig.root, KEY, state="shipped", repo="kuhyx/kartka", title="t", count=1, starts=1,
               commit="c", shipped_at=7.0)  # fmt: skip
    world.entries(kartka_entry())
    shim(world.tmp / "run.sh", world.hook_log, code=1)
    world.tick()
    assert world.tools("add_task") == []


def test_a_fixed_build_is_unknown_when_the_repo_is_not_cloned(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(_repo: str) -> Path:
        raise NeedsYouError("not cloned", "handed_to_you")

    monkeypatch.setattr("todoimpl.errors.settle.repo_dir", missing)
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    ledger.mark_shipped(world.rig.root, [KEY], "abc123", 2_000_000_000.0)
    world.tick()
    assert world.ledger()[KEY]["fixed_build"] == 0


def test_t2027_the_done_card_of_a_shipped_cycle_is_not_a_ticket(world: World) -> None:
    # The Done card keeps the text of what shipped, signature line included (ClosedNotes).
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    (added,) = world.tools("add_task")
    shipped = RunState(
        task_id=CARD, stage="shipped", repo="kuhyx/kartka", note_body=added["body"], extra={"repotask": True}
    )
    save(run_dir(world.rig.root, CARD), shipped)
    world.fake.store.notes.clear()  # the part is closed: no open note is left, only the Done card
    world.rig.backend.cache.refresh()
    assert any(c.status == "done" and KEY in c.body for c in world.rig.backend.cache.snapshot().tasks)
    world.reason = "weekly"
    world.tick()
    assert world.starts() == []  # a Done card is never started
    assert world.ledger()[KEY]["missing"] == 1  # and its text does not keep the ticket alive
    world.tick()
    assert len(world.tools("add_task")) == 2
