"""T2523: the `(kuhy)` mark counts in every head plans write, not only `C9. (kuhy)` (card c96b7ce5).

`parse_criteria` kept `C9.` of `- C9. (kuhy) ...` in front of the mark, so `kuhy_ids` and the sole-approve
hash never saw it: an approval criterion written with a leading dash shipped without kuhy's approve.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from runnerfakes import FakeClient
from todoimpl.runner import crithash
from todoimpl.runner.approval import kuhy_ids, owed
from todoimpl.runner.parsing import parse_criteria

MAIL = "kuhy approves the mail in the board ask, then it is sent"
HEADS = (  # every head a plan writes or might write for criterion 2
    "C2. (kuhy)",
    "- C2. (kuhy)",
    "- C2: (kuhy)",
    "* C2) (kuhy)",
    "C2 (kuhy)",
    "**C2** (kuhy)",
    "**C2.** (kuhy)",
    "- **C2**: (kuhy)",
    "C2 [a1-0]: (kuhy)",
    "- C2 [a1-0]: (kuhy)",
    "- C2. (kuhy) [a1-0]:",
    "2. (kuhy)",
    "- (kuhy)",
)
OLD = (  # heads that already counted: the hash kuhy's stored approve carries must not move
    ("C2. (kuhy) " + MAIL, MAIL),
    ("C2 [a1-0]: (kuhy) " + MAIL, MAIL),
    ("C2. (kuhy) [a1-0]: " + MAIL, "[a1-0]: " + MAIL),
    ("2. (kuhy) " + MAIL, MAIL),
    ("- (kuhy) " + MAIL, MAIL),
    ("C2. " + MAIL, MAIL),
)


def _plan(head: str) -> str:
    return f"## Acceptance criteria\n- C1. I open the draft\n{head} {MAIL}\n## Notes\n"


def _stub(plan: str, run_dir: Path) -> Any:
    fake = SimpleNamespace(
        state=SimpleNamespace(extra={}, sessions={}, task_id=""),
        item=SimpleNamespace(title="t", repo="kuhyx/demo"),
        ctx=SimpleNamespace(client=FakeClient(), run_dir=run_dir),
        plan_md=lambda: plan,
        save=lambda: None,
    )
    return cast("Any", fake)


@pytest.mark.parametrize("head", HEADS)
def test_t2523_every_head_marks_the_criterion_kuhys(head: str, tmp_path: Path) -> None:
    plan = _plan(head)
    criteria = parse_criteria(plan)
    assert len(criteria) == 2
    assert kuhy_ids(criteria) == ["C2"]
    assert owed(_stub(plan, tmp_path), criteria) == "live_check"  # the gate holds until he approves
    assert crithash.for_ask(plan, "review") == crithash.for_ask(plan, "c2")  # the sole approve finds it
    assert (
        crithash.normalise(f"{head} {MAIL}").removeprefix("[a1-0]: ") == MAIL
    )  # a mark-first part key stays


@pytest.mark.parametrize(("line", "words"), OLD)
def test_t2523_heads_that_counted_keep_their_hash(line: str, words: str) -> None:
    assert crithash.normalise(line) == words


@pytest.mark.parametrize(
    "line",
    [
        "1. Open a (kuhy) review ask on the board",
        "C2 Decision (kuhy): drop it",
        "- C2. done (kuhy)",
        "- C2. done",
    ],
)
def test_t2523_a_mark_inside_the_text_is_no_mark(line: str) -> None:
    assert kuhy_ids(parse_criteria(f"## Acceptance criteria\n- C1. x\n{line}")) == []


def test_t2523_a_dashed_phone_check_stays_claudes() -> None:
    phone = "- C2. (kuhy) [a8840600-0]: kuhy rates his normal reviews on the phone while the watcher runs"
    assert kuhy_ids(parse_criteria(f"## Acceptance criteria\n- C1. (kuhy) {MAIL}\n{phone}")) == ["C1"]
