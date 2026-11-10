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
| T1850 | A plan limit paused every run although the Max plan's free API credits could pay: credit turns (Agent SDK, sonnet) now take over while the limit is active, the setting is on and the key is usable, and only then | tests/runner/test_runner_credits_flow.py, tests/credits/test_credits_units.py, tests/service/test_service_credits.py, tests/board/test_board_actions.py |
| T1851 | The API key could reach a plan turn through the server's env, where it takes precedence over the plan login and bills the key | tests/runner/test_runner_credit_build.py |
| T1852 | A credit-balance error read as a transient "API Error" and would have looped in backoff; credits running out now pauses until the plan limit resets and says so | tests/runner/test_runner_credits_flow.py, tests/service/test_service_credits.py |
| T1853 | A plan turn that started spending overage (money) ran on to its end; the overage guard kills it at once, pauses runs and raises a banner | tests/runner/test_runner_credits_flow.py, tests/runner/test_runner_credit_units.py, tests/service/test_service_credits.py |
| T1854 | The phone-last flow was tied to plan turns; a credit turn rests on `A: phone:` and resumes into the attached live check the same way | tests/runner/test_runner_credits_flow.py |
| T1856 | A note titled MANUAL WORK REQUIRED: could be started on Claude; it is human work with a disabled start | tests/runner/test_runner_manual.py, tests/service/test_service_credits.py |
| T1836 | Checks and git ran with the server's `VIRTUAL_ENV` and `.venv/bin` on `PATH`, so a target repo's pre-commit used the server's python and broke | tests/runner/test_runner_checks.py |
| T1837 | Ship left no gate receipt, so a target repo's pre-push hook refused the push (tunedeck, steam-backlog-enforcer, teatr-pw) | tests/runner/test_runner_ship_gate.py |
| T1838 | A push refused because origin moved failed the ship instead of rebasing onto origin and pushing again | tests/runner/test_runner_ship_gate.py |
| T1839 | A clone in a differently named directory (kuhyx/todo-app at ~/src/todo) was "not cloned": the runner looked up the bare name, so the origin scan never ran | tests/board/test_board_repo_path.py |
| T1840 | Gates of several cards ran at once and OOM-killed each other in capped.slice (tunedeck, teatr-pw), failing their ships for no code reason | tests/runner/test_runner_gate.py |
| T1860 | A new task worktree lacked the git-ignored, machine-local android/local.properties (chaquopy.buildPython), so tunedeck's gate and ship failed; the runner now copies a named list of ignored machine-local files | tests/runner/test_runner_worktree_local.py |
| T1861 | The gate steps ran with CAP_CPU_PCT=25, above capped.sh's 20 % ceiling, so every step failed (teatr-pw ts-typecheck) | tests/runner/test_runner_gate.py |
| T1862 | Board sessions were told "never commit, push or touch main, every call under 60 s", so they parked cards on asks that were only permission (commit, merge, push, tags, installers, marker files); the prompts now carry kuhy's standing grant to land their own work | tests/prompts/test_build.py |
| T1863 | A turn ending on an `A:` that only asked permission (OK me, may I, press Retry, send a `LONG:` turn, write it by hand) parked the card; the runner now resumes the session once with a fixed grant and parks only on a second ask | tests/runner/test_runner_ask_grant.py |
| T1864 | A reused worktree kept its old base, so a card started from a tree that lacked work already on origin (s7 beats); each drive now rebases it with autostash, leaves a conflict for the session and tells the prompt | tests/runner/test_runner_worktree_rebase.py |
| T1865 | Ship could not close a branch the session had already pushed ("Nothing to ship") and would have squashed pushed commits again; it now closes with "Pushed by the session: <shas>" and squashes only what origin lacks | tests/runner/test_runner_ship_landed.py |
| T1866 | The every-drive rebase could run in the Ship drive or under a still-running adopted turn, and Ship could commit autostash conflict markers as resolved; the rebase now skips both and Ship refuses a tree with unresolved conflicts | tests/runner/test_runner_worktree_rebase.py |
| T1883 | The umbrella manager armed a Monitor on `pgrep -f <worker path>` (matches itself, never ends) and ended its turn with `R:` before any CHILD line; its prompt now says to poll with short Bash calls and never end the turn early | tests/prompts/test_umbrella_wait.py |
| T1884 | A free worker's "no edit" issue line held the last 500 chars of its log, which were Claude Code startup warnings, and left `model` null; the warnings are dropped and the model is read from the log | tests/umbrella/test_freeworker.py |
| T1886 | The server's round checks ran `pre-commit run --all-files` in a fresh child worktree with no `.venv`, so the hooks failed ("Executable `.venv/bin/python` not found") and the width could never double; the manager prompt now says to build the environment first | tests/prompts/test_umbrella_wait.py |
| T1887 | A free worker misread a textgate child ("Focus Guard" is a proper noun, no changes needed, exit 3) and the Sonnet manager did the rework itself instead of improving the prompt; managers now diagnose and coach the worker (up to 3 retries, `coached <n>` verdict counts toward doubling, `fixed` never does, a `fixed` free child with fewer than 3 `prompt` issue lines is warned about) and textgate task files carry the rules | tests/prompts/test_coaching.py, tests/umbrella/test_flow_coached.py, tests/umbrella/test_ramp.py, web/src/components/umbrella.test.ts |
| T1888 | Cancelling an umbrella mid-round and restarting it re-ran the manager in the dead turn's session (a resume-after-kill prompt, the old model and no rules); a round's manager now always starts a fresh session with the manager prompt, and a task file written before the textgate rules existed gets them on top | tests/umbrella/test_flow_coached.py |
| T1901 | State, mark, setting and plan files were written with tmp + rename but no fsync, so a power cut could leave an empty or torn JSON; every writer now goes through `todoimpl.atomic` (file sync, rename, directory sync) | tests/test_atomic.py |
| T1902 | A turn killed by a signal (OOM, SIGKILL, reboot) was a 3-strike crash, and for an umbrella manager it escalated every child of the round to Opus; it is now its own bounded retry (5, on the 1/2/5/10/30 min ladder) with a reason kind, and never an escalation | tests/resilience/test_killed_turns.py, tests/umbrella/test_resilience.py |
| T1903 | A free worker SIGKILLed after a partial edit exited 0 and read as success; a signal death is logged as phase `killed`, retried 3 times and then exits 5 whatever the tree holds | tests/umbrella/test_freeworker_kill.py |
| T1904 | With no internet or an unreachable gateway an umbrella round spent a Sonnet manager turn doing the free work itself (or failed the turns); the round now rests as `paused_retry` with a reason kind and retries on the backoff ladder | tests/umbrella/test_outage.py |
| T1905 | After a restart an umbrella child found in `shipping` was shipped again at once (and a child reset to the gate by Retry was never saved); it now fails with the interrupted-ship text and Retry returns it to the gate | tests/umbrella/test_restart_ship.py |
| T1907 | A reboot leaves the manager's and a child's turn with no exit record; both resume their stored session once with the kill note and no child is started twice | tests/umbrella/test_reboot.py |
| T1889 | A board restart during the checks left the old `make test` running (KillMode=process) while the new server ran the checks again in the same worktree; the two runs deleted each other's `.coverage.*` files and the gate reported 49 % coverage; a check run now stops the run a previous server left in its run dir (`checks.pgid`, start time guards a reused pid) | tests/runner/test_runner_checks_guard.py |
| T903 | After a red re-run (closing turn or Close click) a failed closing run still offered Start: autocheck.json kept the earlier pass until the next 5-minute tick | tests/runner/test_runner_autoclose.py |
| T904 | Cancel abandons the note, so the poll skips it, yet a cancelled closing run's Restart said "auto close is off, or the first tick has not run" | tests/board/test_board_closing.py |
| T1890 | Even with T1889, the live board (older build) re-ran the checks after a restart while the old `make fast` still ran; both `make test` runs shared `.coverage.*` in the worktree and the gate reported 53 %; `make test` now keeps its coverage data in its own temp dir, so overlapping runs cannot clobber each other | tests/test_makefile_coverage.py |
