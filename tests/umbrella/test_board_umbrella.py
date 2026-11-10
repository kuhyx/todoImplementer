"""Board side of an umbrella: one status rule, one card with child counts, its actions and drawer detail."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from todoimpl.board import umbrella as bu
from todoimpl.board.actions import actions
from todoimpl.board.card import Context, build_card
from todoimpl.board.state import RunState
from todoimpl.board.status import Status, compute
from todoimpl.board.types import Limit
from umbrellafakes import sample

NOW = 1_793_880_000.0


def run(**fields: Any) -> RunState:
    return replace(RunState(task_id="u0000001-0", stage="implement", updated=NOW), **fields)


def ctx() -> Context:
    return Context(now=NOW)


@dataclass(frozen=True)
class Umb:
    """A note-like umbrella card task (no repo)."""

    id: str = "u0000001-0"
    title: str = "Make the repos text-free"
    body: str = sample()
    repo: str | None = None
    status: str = "todo"
    priority: str = "high"
    done_check: str | None = None
    created_by: str = "kuhy"


def _rows(*statuses: str) -> list[dict[str, object]]:
    return [{"id": f"k{i}-0", "status": s} for i, s in enumerate(statuses)]


def test_an_umbrella_without_a_repo_is_backlog_not_yours() -> None:
    assert compute(Umb(), None, False, None) == Status.BACKLOG  # noqa: FBT003
    assert compute(replace(Umb(), body="plain", repo=None), None, False, None) == Status.YOURS  # noqa: FBT003


def test_umbrella_runs_follow_the_normal_rules() -> None:
    assert compute(Umb(), run(stage="implement"), True, None) == Status.WORKING  # noqa: FBT003
    assert compute(Umb(), run(stage="gate"), False, None) == Status.READY_TO_SHIP  # noqa: FBT003


def test_start_is_offered_without_a_repo_and_auto_ship_is_enabled() -> None:
    (start, *_) = actions(Umb(), None, Status.BACKLOG, Limit(), now=NOW)
    assert (start.id, start.enabled, start.reason) == ("start", True, None)
    assert start.option is not None
    assert start.option.enabled


def test_ship_is_enabled_at_the_gate_with_the_run_dir_as_worktree() -> None:
    gate = run(stage="gate", worktree="/x/run")
    ship = next(a for a in actions(Umb(), gate, Status.READY_TO_SHIP, Limit(), now=NOW) if a.id == "ship")
    assert ship.enabled


def test_buckets() -> None:
    assert [bu.bucket(s) for s in ("done", "working", "queued", "shipping", "paused_limit")] == [
        "done",
        "running",
        "running",
        "running",
        "running",
    ]
    assert [bu.bucket(s) for s in ("ready_to_ship", "backlog", "needs_you", "yours", "cancelled")] == [
        "ready",
        "queued",
        "failed",
        "failed",
        "failed",
    ]


def test_counts_come_from_the_note_before_any_run() -> None:
    view = bu.card_view(Umb(), None)
    assert view is not None
    assert view["queued"] == 3
    assert (view["total"], view["width"], view["round"], view["issues"]) == (3, 1, 0, 0)
    ticked = replace(Umb(), body=Umb().body.replace("- [ ] kuhyx/beta", "- [x] kuhyx/beta"))
    after = bu.card_view(ticked, None)
    assert after is not None
    assert (after["done"], after["queued"]) == (1, 2)


def test_counts_come_from_the_rows_of_a_run() -> None:
    rows = _rows("done", "working", "working", "ready_to_ship", "needs_you", "backlog")
    rows[1]["issues"] = 2
    rows[4]["issues"] = 1
    record = {"width": 4, "rounds": [{"n": 1}, {"n": 2}]}
    state = run(extra={bu.VIEW: {"rows": rows}, "umbrella": record})
    assert bu.card_view(Umb(), state) == {
        "done": 1,
        "running": 2,
        "ready": 1,
        "queued": 1,
        "failed": 1,
        "total": 6,
        "width": 4,
        "round": 2,
        "issues": 3,
    }


def test_a_plain_note_has_no_umbrella_view() -> None:
    plain = replace(Umb(), body="plain", repo="kuhyx/x")
    assert bu.card_view(plain, None) is None
    assert bu.detail(plain, None) is None


def test_the_card_carries_the_view_only_for_umbrellas() -> None:
    card = build_card(Umb(), None, ctx())
    assert card["umbrella"]["total"] == 3
    assert card["assignee"] == "claude"
    assert card["status"] == "backlog"
    assert "umbrella" not in build_card(replace(Umb(), body="plain", repo="kuhyx/x"), None, ctx())


def test_detail_lists_rows_and_rounds() -> None:
    record = {"width": 2, "rounds": [{"n": 1, "width": 1, "next": 2, "children": []}]}
    state = run(extra={bu.VIEW: {"rows": _rows("done")}, "umbrella": record})
    assert bu.detail(Umb(), state) == {
        "width": 2,
        "round": 1,
        "rows": _rows("done"),
        "rounds": record["rounds"],
    }
    from_note = bu.detail(Umb(), None)
    assert from_note is not None
    assert [r["repo"] for r in from_note["rows"]] == ["kuhyx/alpha", "kuhyx/beta", "kuhyx/gamma"]
    assert from_note["rounds"] == []
