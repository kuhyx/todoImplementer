"""T2534: a turn that resumed a session claude no longer has dropped it, so every retry failed the same way.

Seen on the sandbox (task 21b9c44a-0): after the 95 % stop a public card went `free` and its retries all ended
"No conversation found with session ID: ..." with the card looping on "retrying".
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from adoptfakes import env, go, rig
from todoimpl.board.state import RunState
from todoimpl.runner import session
from todoimpl.runner.turn import run_turn

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

GONE = "No conversation found with session ID: gone-1"


def _failed_resume() -> dict[str, str]:
    result = {
        "type": "result", "subtype": "error_during_execution", "is_error": True, "num_turns": 0,
        "session_id": "gone-1", "result": "", "errors": [GONE],
    }  # fmt: skip
    return {"_fake": "raw", "text": json.dumps(result)}


def test_t2534_a_lost_session_is_forgotten_and_the_retry_starts_fresh(world: Env, tmp_path: Path) -> None:
    run_dir, wt = rig(world, tmp_path)
    world.script("abcd1234", {"_fake": "bare"}, _failed_resume())
    world.script("abcd1234", {"_fake": "result", "text": "D: ok"})
    st = RunState(task_id="abcd1234-0", stage="plan")
    st.sessions["plan"] = {"session_id": "gone-1", "last_turn_end": 99.0}
    events: list[dict[str, object]] = []
    res = run_turn(env(run_dir, wt, events), st, "plan", go)
    assert res.is_error
    assert GONE in res.text  # the card shows why, not just "turn ended (error_during_execution)"
    assert "plan" not in st.sessions
    run_turn(env(run_dir, wt, events), st, "plan", go)
    assert [c["resume"] for c in world.calls()] == ["gone-1", None]


def test_t2534_both_claude_texts_count_as_a_lost_session() -> None:
    assert session.lost(
        "Error: --resume requires a valid session ID or session title when used with --print."
    )
    assert session.lost(GONE)
    assert not session.lost("rate limited")
