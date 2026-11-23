"""T2522: a check that needs phone interaction is Claude's, never an ask for kuhy (card c96b7ce5-0, tutor).

The note said "Check: manual (needs the phone and a live deploy)", the plan wrote `C9. (kuhy) kuhy rates his
normal reviews on the phone ...`, and the sessions ended `A:` with an approve choice plus a watcher command,
so the card rested in Needs you asking kuhy to rate reviews on his phone.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from todoimpl.prompts import PromptContext, build
from todoimpl.runner import askform
from todoimpl.runner.approval import kuhy_ids

WATCH = (
    "command c9-watch: R=~/.local/lib/tutor-live/current; "
    "systemctl --user is-active -q tutor-review-watch || "
    'systemd-run --user --collect --unit=tutor-review-watch -p RuntimeMaxSec=1800 -E PYTHONPATH="$R" '
    '~/src/tutor/.venv/bin/python "$R/scripts/review_due_watch.py"'
)
ASKS = (  # the card's own ask blocks, verbatim
    (
        "choice c9: Approve C9 after your next phone review (delays logged to "
        "~/.local/state/tutor/review_due_watch.jsonl) | *approve | change"
    ),
    (
        "choice c9: Rate reviews on the phone while the watcher runs; the first 3 land in log.jsonl "
        f"under 5 s | *approve | change\n{WATCH}"
    ),
    (
        "choice c9: Rate a few reviews on the phone before 08:30; the first 3 must land in log.jsonl "
        f"under 5 s each | *approve | change\n{WATCH}"
    ),
)
KUHYS = (  # asks only kuhy can answer stay with him
    "choice c2: Approve the logo for the phone app | *approve | change",
    "choice c1: Caddy block | yes | *no | risk=reversible",
    "choice c9: Rate reviews on the phone | *approve | change\ncommand k1: sudo systemctl restart tutor",
)
C9 = (
    "C9. (kuhy) [a8840600-0]: kuhy rates his normal reviews on the phone while `review_due_watch` runs. "
    "Its file under `~/.local/state/tutor/` shows the first 3 ratings landing in `log.jsonl` under 5 s each."
)
MAIL = "C2. (kuhy) kuhy approves the mail in the board ask, then it is sent"
LOGO = "C3. (kuhy) kuhy approves the logo in the board ask, then it is installed on the phone"


def _driver(block: str) -> Any:
    reply = f"All parts are ticked; C9 needs reviews rated on your phone.\n\n```ask\n{block}\n```\n\nA: rate"
    st = SimpleNamespace(extra={"last_reply": reply})
    return SimpleNamespace(state=st, activity=lambda _t: None, save=lambda: None)


def _res() -> Any:
    return SimpleNamespace(tag="A", is_error=False, denials=[])


@pytest.mark.parametrize("block", ASKS)
def test_t2522_an_ask_for_phone_work_goes_back_to_the_session(block: str) -> None:
    driver = _driver(block)
    assert askform.needs_form(driver, _res(), "implement")
    note = driver.state.extra["granted_note"]
    assert "phone_vd.sh" in note
    assert "never kuhy's" in note


@pytest.mark.parametrize("block", KUHYS)
def test_t2522_a_real_decision_or_a_root_command_stays_with_kuhy(block: str) -> None:
    driver = _driver(block)
    assert not askform.needs_form(driver, _res(), "implement")
    assert "granted_note" not in driver.state.extra


def test_t2522_a_phone_check_marked_kuhy_is_not_his_to_approve() -> None:
    plan = ["C1. I open the app, I see it", C9.removeprefix("C9. "), MAIL.removeprefix("C2. ")]
    assert kuhy_ids(plan) == ["C3"]
    assert kuhy_ids([LOGO.removeprefix("C3. ")]) == ["C1"]  # an approval stays kuhy's, phone or not


def test_t2522_prompts_tell_sessions_to_run_phone_checks_themselves(tmp_path: Path) -> None:
    ctx = PromptContext(title="t", body="", repo="r", worktree=tmp_path, run_dir=tmp_path)
    assert "never mark it `(kuhy)`" in build("plan", ctx)
    for stage in ("implement", "live_check", "fix"):
        text = build(stage, ctx)
        assert "needs phone interaction (taps, ratings, screenshots, timing on the device)" in text, stage
        assert "never ask kuhy to rate, tap" in text, stage
