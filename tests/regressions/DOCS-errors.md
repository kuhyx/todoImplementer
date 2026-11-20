# App-error regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...` (pytest) or titled `[T<N>] ...` (vitest). The feature is `DOCS-errors.md`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T2009 | An app error produced no card: nothing turned an open error of a source into one ticket on the repo's card and started it | tests/errors/test_loop.py |
| T2010 | The same error made a second ticket on every tick, and a lost ledger made a duplicate instead of finding the ticket by its `Error-Signature:` line | tests/errors/test_loop.py |
| T2011 | A ticket made while weekly usage was high was forgotten: the gate is checked on every tick, so the card starts after the reset or when credits are back | tests/errors/test_loop.py |
| T2012 | A burst of errors in several repos started every card at once and overshot the usage limit: at most one card starts per tick | tests/errors/test_loop.py |
| T2013 | Free models were allowed by the gate but the card stayed on the plan: the ticket now gets `Tier: cheap` before it starts for that reason | tests/errors/test_loop.py |
| T2014 | A card at work, failed or at its gate was started again, and a shipped cycle with parts left never began its next cycle | tests/errors/test_loop.py |
| T2015 | A part the session never ticked was started again forever: at most three starts per ticket | tests/errors/test_loop.py |
| T2016 | The count in the ticket was rewritten on every tick (note spam): only a changed count writes the `Seen:` line | tests/errors/test_loop.py |
| T2017 | A shipped fix was never reported to its source: the resolve hook runs after Ship, a failing hook is retried, `fixed_build` is the build of the pushed commit | tests/errors/test_loop_fixed.py |
| T2018 | A report from a build older than the fixed one reopened a fixed error; one from the fixed build or newer did not | tests/errors/test_loop_fixed.py |
| T2019 | With no build ids in the source, an old event the phone sent late reopened a fixed error: only an event after the install counts | tests/errors/test_loop_fixed.py |
| T2020 | An error fix waited at Ready to ship for kuhy's click (it had no `done_check`), or a card of kuhy's own was shipped by an error run | tests/runner/test_runner_ship_appfix.py |
| T2021 | A fix pushed while the phone was away read as an ordinary failed deploy that needs kuhy | tests/runner/test_runner_ship_appfix.py |
| T2022 | The phone connecting did not finish the update: the deploy reran only on kuhy's Retry, and a deploy that kept failing looped forever | tests/runner/test_runner_ship_appfix.py |
| T2023 | The board had no status for "fix pushed, wait for the phone, then update the app" | tests/board/test_board_appfix.py |
| T2024 | A card holding app-error tickets looked like any other card | tests/board/test_board_appfix.py |
| T2025 | Which parts an error run may ship alone was undefined: kuhy's own ticked part rides along and waits at the gate | tests/errors/test_marks.py |
| T2026 | An error run asked kuhy questions instead of answering them itself (bounce, grant) | tests/errors/test_marks.py |
| T2027 | The Done card of a shipped cycle keeps the signature line of what it shipped and counted as the open ticket: a regression got no new ticket and the loop tried to start a Done card | tests/errors/test_loop_fixed.py |
| T2402 | Five running cards sat ~47 min with no activity and nothing noticed it. A watch now checks every 10 s: a card with a live turn whose last real `activity` event is over 60 s old (board `system` lines and heartbeats do not count) is logged in `stalls.jsonl` and counted in the contract report as `perf.stall` (`stall-memory`, `stall-buildlock`, `stall-job-<tool>`, `stall-model`), once per episode | tests/stall/test_stall_watch.py, tests/stall/test_stall_cause.py, tests/stall/test_stall_edges.py |
| T2403 | A stall ticket waited behind the usage gate and other error cards. The errors loop now starts stall tickets first and skips the usage gate for them (reason `stall`) | tests/errors/test_loop_stall.py |
