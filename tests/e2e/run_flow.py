#!/usr/bin/env python3
"""Ground-truth flow F1 (Q11) against the real server, one step per call so each stays under 60 s.

    run_flow.py step 1 [--real-claude]  scratch HOME, repo, bare origin, fake todo MCP seeded with 3 items
    run_flow.py step 2                  start `python -m todoimpl.http.main` detached, poll /version
    run_flow.py step 3                  GET /api/board (3 cards in Backlog), POST start on all, live feed
    run_flow.py step 4                  wait for every card to ship (<= 3 at once; plan, live_check, checks)
    run_flow.py step 5                  wait for each ship: remote commits with Todo trailers, notes done
    run_flow.py step 6                  stop all, keep artefacts in ~/data/claude-scratch/e2e, rm work dir
    run_flow.py status | step 3-5       state of the run in progress | consecutive steps

Exit 0 = step passed, 1 = FAIL (artefacts saved, failing step printed), 3 = still running (run it again).
--real-claude (step 1 only, sticks for the run): real `claude` on haiku, the single note only (manual smoke).
"""

from __future__ import annotations

import argparse
import sys

from e2e_flow import step3_board_and_start, step4_wait_ready, step5_ship
from e2e_log import TOTAL, FailError, PendingError, fail, save_artifacts, say
from e2e_setup import step1_setup, step2_server, step6_teardown
from e2e_world import State, load

STEPS = {
    2: step2_server,
    3: step3_board_and_start,
    4: step4_wait_ready,
    5: step5_ship,
    6: step6_teardown,
}


def run_step(number: int, state: State | None, *, real_claude: bool) -> State:
    """Run one step; step 1 creates the state, the others need it."""
    if number == 1:
        return step1_setup(real_claude)
    if state is None:
        msg = "no run in progress: run `step 1` first"
        fail(msg)
    STEPS[number](state)
    return state


def parse_steps(text: str) -> list[int]:
    """`3` -> [3]; `3-5` -> [3, 4, 5]."""
    first, _, last = text.partition("-")
    numbers = list(range(int(first), int(last or first) + 1))
    if not numbers or min(numbers) < 1 or max(numbers) > TOTAL:
        msg = f"steps are 1..{TOTAL}"
        raise SystemExit(msg)
    return numbers


def main(argv: list[str]) -> int:
    """CLI entry; returns the exit code described in the module docstring."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    step = sub.add_parser("step")
    step.add_argument("which", help="1..6 or a range like 3-5")
    step.add_argument("--real-claude", action="store_true")
    args = parser.parse_args(argv)
    state = load()
    if args.cmd == "status":
        print(state or "no run in progress")
        return 0
    current = 0
    try:
        for current in parse_steps(args.which):
            state = run_step(current, state, real_claude=args.real_claude)
            print(f"PASS {current}/{TOTAL}", flush=True)
    except PendingError as pending:
        print(f"PENDING F1 step {current}/{TOTAL}: {pending}; run `step {current}` again", flush=True)
        return 3
    except (FailError, AssertionError) as exc:
        where = ""
        if state is not None:
            say(state, current, f"FAIL {exc}")
            where = f"; artefacts: {save_artifacts(state, f'fail-step{current}')}; work dir {state.work}"
        print(f"FAIL F1 step {current}/{TOTAL}: {exc}{where}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
