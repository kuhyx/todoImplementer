# Runner regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T301 | A resumed session's total_cost_usd is cumulative; summing it per turn double-counted the cost | tests/runner/test_runner_scheduler_more.py |
| T302 | A restart re-ran every run resting on a Q/A tag, re-sending its last turn | tests/runner/test_runner_scheduler_more.py |
| T303 | Ship's commit and rebase used the 50 s git timeout, so slow pre-commit hooks failed the ship | tests/runner/test_runner_ship.py |
| T902 | A restart left the old claude turn running (KillMode=process) and recovery resumed the same session in the same worktree, so two sessions edited it at once (only the recorded turn pid is reaped, never kuhy's own session) | tests/runner/test_runner_scheduler_more.py |
| T1201 | A turn that died offline went to Needs you instead of waiting for the network | tests/runner/test_runner_selfheal.py |
| T1202 | A crashing turn went to Needs you at once, and without the stderr that explains it | tests/runner/test_runner_selfheal.py |
| T1203 | A turn killed by a signal with empty stderr was not retried | tests/runner/test_runner_selfheal.py |
| T1204 | Retry waits were not 1 min, 5 min, 30 min, then hourly | tests/runner/test_runner_selfheal.py |
| T1205 | Network, 5xx and overload text was not told apart from a crash | tests/runner/test_runner_selfheal.py |
| T1206 | The stderr log of a turn was never read | tests/runner/test_runner_selfheal.py |
| T1207 | An unreachable todo MCP at drive start failed the run | tests/runner/test_runner_selfheal.py |
| T1208 | A restart lost a paused retry, or ran it before its resume time | tests/runner/test_runner_selfheal.py |
| T1209 | Headless claude killed background subagents 10 min after the last turn | tests/runner/test_runner_selfheal_env.py |
| T1210 | The fresh-session handoff dropped the self-check and the live-check report | tests/runner/test_runner_selfheal_env.py |
| T1211 | state.json was replaced without an fsync of its directory | tests/runner/test_runner_selfheal_env.py |
| T1212 | A repeated unreachable read lost the stage a paused retry resumes | tests/runner/test_runner_selfheal.py |
| T1213 | A note from kuhy did not end a retry wait | tests/runner/test_runner_selfheal.py |
| T1214 | A card waiting to retry showed the bare stage, not when and why | tests/board/test_board_board.py |
| T1220 | Three turns without a status tag went straight to Needs you | tests/runner/test_runner_tagless.py |
| T1221 | A fresh session that ended tagless again did not stop at Needs you | tests/runner/test_runner_tagless.py |
| T1222 | An `R:` turn was nudged as tagless instead of continued | tests/runner/test_runner_tagless.py |
| T1223 | `R:` continues had no cap of three | tests/runner/test_runner_tagless.py |
| T1224 | Retry on a failed card restarted at plan, not at the failed stage | tests/runner/test_runner_tagless.py |
| T1225 | Retry of a failed ship restarted the whole run | tests/runner/test_runner_tagless.py |
| T1226 | A commit hook failure at ship went to Needs you instead of a fix turn | tests/runner/test_runner_tagless.py |
| T1227 | The ship error embedded the whole commit message and no cap bounded the fixes | tests/runner/test_runner_tagless.py |
| T1103 | A plan criterion missing from the live-check report passed silently instead of counting as not done | tests/runner/test_runner_live.py |
| T1104 | A live-check turn that delegated to a background agent and ended with `R:`/`D:` and no checklist failed the task ("no `- [x]` lines") instead of being re-run | tests/runner/test_runner_live.py |
| T1108 | Criteria that can only pass after the ship (or need the phone) had no `- [~]` row and failed the live check | tests/runner/test_runner_parsing.py |
| T1109 | One criterion still open after the live fix sent a card with the rest done to Needs you instead of accepting it partly with one follow-up note | tests/runner/test_runner_live.py |
| T1110 | The live-check parser dropped rows without a dash, with `**C1**` or without a colon | tests/runner/test_runner_parsing.py |
| T1228 | A live check ending `R:` was redone as checklist-less instead of continued first | tests/runner/test_runner_live.py |
| T1808 | A live check that ended on a prose summary twice failed the run as "Needs you"; the redo resent the whole verify prompt in the same long session, so the model re-verified and summarised again | tests/runner/test_runner_live_ladder.py |
| T1809 | Runs failed at the live check before partial acceptance landed (12 of 13 done) stayed in Needs you: a failed run was never judged again when the rules changed | tests/runner/test_runner_rejudge.py |
| T1810 | A follow-up note the todo app failed to add sent a run with done criteria to Needs you instead of retrying on a timer with no turn | tests/runner/test_runner_rejudge.py |
| T1813 | A follow-up note listed only the open criteria with no link back, so it read as if the earlier task did nothing | tests/runner/test_runner_live.py, web/src/components/sections.test.ts |
| T1814 | A done_check written as a sentence ran as a bash command, so its run could never pass Checks | tests/runner/test_runner_checks.py |
| T1817 | A server restart or deploy reaped the running claude turns and reran them: the turn was a child pipe of the server, so changing the server affected live sessions | tests/runner/test_runner_detach.py, tests/runner/test_runner_launch.py, tests/runner/test_runner_adopt.py, tests/deploy/test_deploy_script.py |
| T1836 | Checks and git ran with the server's `VIRTUAL_ENV` and `.venv/bin` on `PATH`, so a target repo's pre-commit used the server's python and broke | tests/runner/test_runner_checks.py |
| T1837 | Ship left no gate receipt, so a target repo's pre-push hook refused the push (tunedeck, steam-backlog-enforcer, teatr-pw) | tests/runner/test_runner_ship_gate.py |
| T1838 | A push refused because origin moved failed the ship instead of rebasing onto origin and pushing again | tests/runner/test_runner_ship_gate.py |
