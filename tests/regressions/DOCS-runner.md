# Runner regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T301 | A resumed session's total_cost_usd is cumulative; summing it per turn double-counted the cost | tests/runner/test_runner_scheduler_more.py |
| T302 | A restart re-ran every run resting on a Q/A tag, re-sending its last turn | tests/runner/test_runner_scheduler_more.py |
| T303 | Ship's commit and rebase used the 50 s git timeout, so slow pre-commit hooks failed the ship | tests/runner/test_runner_ship.py |
| T902 | A restart left the old claude turn running (KillMode=process) and recovery resumed the same session in the same worktree, so two sessions edited it at once (only the recorded turn pid is reaped, never kuhy's own session) | tests/runner/test_runner_scheduler_more.py |
