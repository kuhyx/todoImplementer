"""kuhy's approve is keyed to the `(kuhy)` criterion's text, not to plan.md's mtime (T2462)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_runner_approval import ALL_TICKED, PLAN, stub
from todoimpl.board.state import RunState, save
from todoimpl.runner import crithash
from todoimpl.runner.approval import approved
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.live import settle

C2 = "(kuhy) kuhy approves the mail in the board ask, then it is sent"


def write(run_dir: Path, plan: str, **items: dict[str, object]) -> float:
    """Write plan.md, then asks.json with records stamped a minute before the plan."""
    (run_dir / "plan.md").write_text(plan, encoding="utf-8")
    planned = (run_dir / "plan.md").stat().st_mtime
    stamped = {k: {"at": planned - 60, "cycle": 1, **v} for k, v in items.items()}
    (run_dir / "asks.json").write_text(json.dumps({"items": stamped}), encoding="utf-8")
    return planned


def ok(crit: str = C2) -> dict[str, object]:
    return {"state": "answered", "answer": "approve", "crit": crithash.digest(crit)}


def test_t2462_plan_rewritten_after_the_approve_keeps_it(tmp_path: Path) -> None:
    write(tmp_path, PLAN.replace("Polish mail", "Polish mail, reworded"), c2=ok())
    assert settle(stub(tmp_path), ALL_TICKED) == "checks"


def test_t2462_rewrap_only_keeps_the_approve(tmp_path: Path) -> None:
    write(tmp_path, PLAN.replace("board ask, then", "board ask,\n   then"), c2=ok())
    assert approved(tmp_path, "C2")


def test_t2462_changed_criterion_says_reapprove_and_reopens(tmp_path: Path) -> None:
    write(tmp_path, PLAN.replace("then it is sent", "then it is posted"), c2=ok())
    with pytest.raises(NeedsYouError, match="approved before the plan changed; re-approve"):
        settle(stub(tmp_path), ALL_TICKED)
    assert "c2" not in json.loads((tmp_path / "asks.json").read_text())["items"]


def test_t2462_stale_change_answer_is_not_said(tmp_path: Path) -> None:
    write(tmp_path, PLAN.replace("then it is sent", "then it is posted"), c2={**ok(), "answer": "change"})
    assert settle(stub(tmp_path), ALL_TICKED) == "live_check"  # the session asks again


def test_t2462_new_cycle_does_not_inherit(tmp_path: Path) -> None:
    write(tmp_path, PLAN, c2=ok())
    save(tmp_path, RunState(task_id="x", stage="live_check", extra={"cycle": 2}))
    assert not approved(tmp_path, "C2")


def test_t2462_no_hash_record_uses_the_mtime_rule_within_its_cycle(tmp_path: Path) -> None:
    planned = write(tmp_path, PLAN, c2={"state": "answered", "answer": "approve"})
    assert not approved(tmp_path, "C2")
    data = {"items": {"c2": {"state": "answered", "answer": "approve", "at": planned + 1, "cycle": 1}}}
    (tmp_path / "asks.json").write_text(json.dumps(data), encoding="utf-8")
    assert approved(tmp_path, "C2")
    data["items"]["c2"]["cycle"] = 0
    (tmp_path / "asks.json").write_text(json.dumps(data), encoding="utf-8")
    assert not approved(tmp_path, "C2")


def test_t2462_sole_fallback_respects_the_hash(tmp_path: Path) -> None:
    review: dict[str, object] = {"state": "answered", "answer": "approve", "crit": crithash.digest(C2)}
    write(tmp_path, PLAN, review=review)
    assert approved(tmp_path, "C2", sole=True)
    write(tmp_path, PLAN.replace("then it is sent", "then it is posted"), review=review)
    assert not approved(tmp_path, "C2", sole=True)
    write(tmp_path, PLAN.replace("then it is sent", "then it is posted"), c2=ok(), review=review)
    assert not approved(tmp_path, "C2", sole=True)  # a stale own record is never overridden


def test_t2462_for_ask_reads_the_criterion_block(tmp_path: Path) -> None:
    plan = "## Acceptance criteria\nC1. a\nC2 [k-1]: (kuhy) b\n  c\n\n## Next\nC3. no\n"
    assert crithash.for_ask(plan, "c2") == crithash.digest("b c")
    assert crithash.for_ask(plan, "review") == crithash.digest("b c")  # the sole (kuhy) criterion
    assert crithash.for_ask(plan, "c3") is None
    assert crithash.for_ask("## Acceptance criteria\nC1. a\n", "review") is None
    assert crithash.normalise("C7 [p-2]:  (kuhy)  x\n y") == "x y"
    assert crithash.from_file(tmp_path / "missing.md", "c1") is None
    (tmp_path / "plan.md").write_text(plan, encoding="utf-8")
    assert crithash.from_file(tmp_path / "plan.md", "c1") == crithash.digest("a")
