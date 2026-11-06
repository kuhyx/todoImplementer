"""Autonomy metrics: unassisted cards, permission asks, questions asked, criteria failed (per ISO week)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autofix import WEEK45, WEEK46, add_interventions, add_live_report, add_turn, make_run, tail
from todoimpl.usage import autonomy_summary

if TYPE_CHECKING:
    from pathlib import Path

CARDS = "\n\n".join(f"❓ **Q{n}** - **t{n}**: body\n➡️ yes" for n in (1, 2))
LIVE_OK = "- [x] C1: ran -> saw\n- [~] C2: phone -> later\n- [ ] C3: ran -> broke\n"


def weekly(metric: dict[str, Any]) -> dict[str, Any]:
    return {row["week"]: row["value"] for row in metric["weekly"]}


def test_empty_root_is_all_zero(tmp_path: Path) -> None:
    out = autonomy_summary(tmp_path / "missing")
    assert out["done_unassisted"] == {
        "value": None,
        "count": 0,
        "finished": 0,
        "target": 100,
        "direction": "up",
        "weekly": [],
    }
    for name in ("permission_asks", "questions_asked", "criteria_failed"):
        assert out[name] == {"value": 0, "target": 0, "direction": "down", "weekly": []}
    assert out["cards"] == 0
    assert out["backfilled"] == 0


def test_unassisted_counts_finished_cards_without_kuhy(tmp_path: Path) -> None:
    ship = {"pushed_at": WEEK45, "closed_at": WEEK45, "commit": "abc"}
    shipped = make_run(tmp_path, "aaaaaaaa-0", "shipped", ship=ship, updated=WEEK46)
    add_interventions(shipped, [(WEEK45, "start")])
    sent = make_run(tmp_path, "bbbbbbbb-0", "gate", updated=WEEK45)
    add_interventions(sent, [(WEEK45, "start"), (WEEK45, "send")])
    make_run(tmp_path, "cccccccc-0", "gate", updated=WEEK46)  # legacy, no trace of kuhy
    make_run(tmp_path, "dddddddd-0", "gate", updated=WEEK46, questions=2, answers=2)  # legacy, answered
    asked = make_run(tmp_path, "eeeeeeee-0", "gate", updated=WEEK46)  # legacy, Claude asked something
    add_turn(asked, "implement", WEEK45, "Q", tail("really?", "Q:"))
    make_run(tmp_path, "ffffffff-0", "implement", updated=WEEK46)  # unfinished
    make_run(tmp_path, "99999999-0", "failed", updated=WEEK46, extra={"failed_stage": "shipping"})
    out = autonomy_summary(tmp_path)["done_unassisted"]
    assert (out["count"], out["finished"], out["value"]) == (3, 6, 50.0)
    assert out["weekly"] == [
        {"week": "2026-W45", "count": 1, "finished": 2, "value": 50.0},
        {"week": "2026-W46", "count": 2, "finished": 4, "value": 50.0},
    ]


def test_every_retry_or_cancel_or_credits_click_is_an_intervention(tmp_path: Path) -> None:
    for number, kind in enumerate(("retry", "cancel", "credits", "go", "spec_ok")):
        run = make_run(tmp_path, f"{number:08d}-0", "gate", updated=WEEK45)
        add_interventions(run, [(WEEK45, kind)])
    assert autonomy_summary(tmp_path)["done_unassisted"]["count"] == 0


def test_legacy_traces_of_kuhy_are_backfilled(tmp_path: Path) -> None:
    sent = make_run(tmp_path, "aaaaaaaa-0", "gate", updated=WEEK45)
    (sent / "events.jsonl").write_text(
        '{"type": "activity", "kind": "user", "at": 1, "seq": 1}\ntorn\n{"kind": "text"}\n[1]\n'
    )
    make_run(tmp_path, "bbbbbbbb-0", "gate", updated=WEEK45, extra={"spec_ok": True})
    make_run(tmp_path, "cccccccc-0", "gate", updated=WEEK45, using_credits=True)
    out = autonomy_summary(tmp_path)
    assert out["done_unassisted"]["count"] == 0
    assert out["backfilled"] == 3


def test_permission_asks_are_a_tagged_turns_that_ask_for_approval(tmp_path: Path) -> None:
    run = make_run(tmp_path, "aaaaaaaa-0", "implement", updated=WEEK46)
    add_turn(
        run, "plan", WEEK45, "A", tail("Run `! textgate approve` for the tiles.", "A: approve the gate edit")
    )
    add_turn(run, "implement", WEEK46, "A", tail("x", "A: plug in and unlock the Pixel"))
    add_turn(run, "implement", WEEK46 + 1, "A", "no tag line at all")
    add_turn(run, "implement", WEEK46 + 2, "D", tail("approve everything", "D: approved"))
    (run / "implement-1.result.json").write_text("not json")
    metric = autonomy_summary(tmp_path)["permission_asks"]
    assert metric["value"] == 1
    assert weekly(metric) == {"2026-W45": 1}


def test_questions_count_spec_cards_and_free_asks_not_cards(tmp_path: Path) -> None:
    run = make_run(tmp_path, "aaaaaaaa-0", "implement", started_at=WEEK45, updated=WEEK46, questions=3)
    add_turn(run, "spec", WEEK45, "Q", tail(CARDS, "Q:"))  # already counted through spec_questions
    add_turn(run, "implement", WEEK46, "Q", tail(CARDS, "Q: which one?"))
    add_turn(run, "implement", WEEK46 + 1, "Q", tail("one thing?", "Q:"))
    make_run(tmp_path, "bbbbbbbb-0", "spec_wait", updated=WEEK46, questions=1)  # no started_at: last save
    metric = autonomy_summary(tmp_path)["questions_asked"]
    assert metric["value"] == 3 + 2 + 1 + 1
    assert weekly(metric) == {"2026-W45": 3, "2026-W46": 4}


def test_criteria_failed_from_partial_and_from_a_settled_report(tmp_path: Path) -> None:
    part = make_run(
        tmp_path,
        "aaaaaaaa-0",
        "gate",
        updated=WEEK46,
        extra={"partial": {"done": ["C1"], "open": ["C2"], "deferred": ["C3", "C4"]}},
    )
    add_live_report(part, LIVE_OK, at=WEEK45)
    report = {"live_check": {"report_md": LIVE_OK, "shots": []}}
    add_live_report(make_run(tmp_path, "bbbbbbbb-0", "checks", updated=WEEK46, **report), LIVE_OK, at=WEEK46)
    stopped = make_run(
        tmp_path, "cccccccc-0", "failed", updated=WEEK46, extra={"failed_stage": "live_check"}, **report
    )
    add_live_report(stopped, LIVE_OK, at=WEEK46)
    midway = make_run(tmp_path, "dddddddd-0", "implement", updated=WEEK46, **report)  # a fix is under way
    add_live_report(midway, LIVE_OK, at=WEEK46)
    no_plan = make_run(tmp_path, "eeeeeeee-0", "gate", updated=WEEK46, live_check={"report_md": "- [ ] x\n"})
    assert not (no_plan / "plan.md").exists()
    metric = autonomy_summary(tmp_path)["criteria_failed"]
    # partial: open 1 + deferred 2; each settled report: C2 deferred + C3 open; with no plan.md only the
    # lines of the report count
    assert weekly(metric) == {"2026-W45": 3, "2026-W46": 2 + 2 + 1}
    assert metric["value"] == 3 + 2 + 2 + 1


def test_unreadable_runs_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "bad00000-0").mkdir()
    (tmp_path / "bad00000-0" / "state.json").write_text("{")
    (tmp_path / "note.txt").write_text("not a run dir")
    (tmp_path / "empty000-0").mkdir()
    run = make_run(tmp_path, "aaaaaaaa-0", "gate", updated=WEEK45)
    (run / "interventions.jsonl").write_text('torn\n{"at": "x", "kind": 1}\n[3]\n{"at": 5, "kind": "send"}\n')
    add_turn(run, "implement", WEEK45, "A", "ask")
    (run / "implement-9.000.stream.jsonl").unlink(missing_ok=True)
    (run / "implement-9.000.result.json").write_text('{"tag": "A"}')
    out = autonomy_summary(tmp_path)
    assert out["cards"] == 1
    assert out["done_unassisted"]["count"] == 0
