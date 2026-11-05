# Lessons carried over from the predecessor

The predecessor was a ticket-to-ship pipeline built for one employer. Its docs, its runner code and about 600
regression rows were read (never copied). Each lesson below ends with how todoImplementer applies it. Everything is
in my own words and carries no employer names, ids or hosts.

## 1. Runner mechanics (headless Claude sessions)

**1.1 One turn is one `claude -p` process whose stream goes to a file.** The predecessor ran
`claude -p <prompt> --model <m> --permission-mode <mode> --output-format stream-json --verbose --add-dir <run dir>
--settings <json>` and let stdout land in `<role>-<epoch>.stream.jsonl`, so the UI can tail the file while the turn runs
and the final `result` event is parsed afterwards (session id, text, cost, turn count).
-> `runner/claude.py` builds the argv as a list (never a shell string), streams to
`<role>-<epoch>.stream.jsonl`, and the SSE feed tails that file. `--verbose` is mandatory with stream-json.

**1.2 Resume by session id; a stream with no result file marks a killed turn.** The result file was written only
after claude exited, so the newest stream without one was a turn killed with its parent (shutdown, crash), unless the
stream already ended on a result event. Starting a new session for it paid for the same work twice (a logged
regression). A resumed killed turn is told what the kill took: child processes are gone, files may be partial.
-> `runner/session.py` implements the same marker and sends a fixed "your previous turn was killed" note on resume.
Turns with an outward effect that is not idempotent are never resumed blind (Ship re-checks the remote first).

**1.3 After an hour idle, start a fresh session.** Prompt-cache entries live about an hour; resuming later rewrites
the whole context at full price. A fresh session with a handoff (plan.md, the last failure) is cheaper.
-> `state.json.sessions[role].last_turn_end`; `session.py` starts fresh when `now - last_turn_end > 3600` and passes
the plan and the previous findings as the handoff.

**1.4 Watch the stream for the plan limit while the turn runs.** The stream carries `rate_limit_event` objects with
`resetsAt`, `utilization`, `isUsingOverage` and per-window blocks (five-hour, seven-day). Lessons: the top-level reset
names only the window limiting now, and both windows can be exhausted, so take the latest reset among windows that
are rejected or at 100 %; never use the overage window's own reset; a turn that crossed the limit still finishes, so
record the limit at once so no other run starts. The watch re-read the whole file every second, which scales badly.
-> `runner/limits.py` keeps a byte offset and parses only new lines; it writes `limit-until` (one epoch, root level)
and `limit-credits`. While `limit-until` is in the future no `claude` starts; paused runs resume at that epoch with no
tokens spent waiting. A limit message without a time (text detection by regex) retries after 30 minutes.

**1.5 Overage is spent only by an explicit per-task click.** "Run on credits" sets a flag for that one task and works
only while the limit is the plan's and credits remain. -> `credits` action; `using_credits` in state.json; the action
is disabled with a reason otherwise.

**1.6 Per-role model; MCP servers differ here by decision.** The predecessor loaded only the servers a role calls
(strict config), because every connected server adds tool definitions to every turn. kuhy chose the opposite
(2026-11-05): work sessions load his full setup and all MCPs, so they behave like his own sessions. -> Per-role
model only (Opus implement, Sonnet spec, Haiku classify); the cost of the tool lists is accepted and visible in the
token usage pages. Only the one-shot Haiku drafter stays minimal.

**1.7 Cap Bash output and deny secrets through `--settings`.** A settings JSON passed per spawn set
`bashOutputMaxChars` (20000 instead of 30000) and a permission deny for reading the secrets file or running a command
naming it; the spawned environment also dropped stored account variables. -> `claude.py` always passes `--settings`
with the same two protections for `~/.config/todoImplementer/` and strips tokens from the child env; it also sets
`CLAUDE_AUTO_CONTINUE=0` so handoff hooks never spawn untracked sessions.

**1.8 The final reply carries a status line; parse the last one.** The predecessor ended replies with `STATUS: x`
and read the last match. -> kuhy's tag convention: the last line starting `Q:`, `A:`, `R:` or `D:` is `last_tag`;
Q or A puts the task in Needs you with the reply as `needs.text`. Missing tag after a clean exit counts as D only if
the checks pass; otherwise Needs you (never silently "fine").

**1.9 One-shot classification is a separate cheap call.** Haiku, `--output-format json`, no tools, strict empty MCP
config, any failure returns "" rather than raising. -> `classify()` in `claude.py`; callers treat "" as "unknown".

**1.10 Name runs exactly.** A lookup by role-name prefix matched a sibling role and resumed the wrong session.
-> Files are `<role>-<10-digit epoch>.stream.jsonl` and lookups match the full role plus digits.

**1.11 A missing tool is a readable error.** `claude` not on PATH ends the run with a one-line cause in `error`,
not a traceback. Child timeouts kill the process group and record the timeout.

## 2. Review loop: read, measured, deliberately not adopted

kuhy's decision (2026-11-05): no AI review loop and no verify/proof stage here, now or later. What the predecessor
taught, and what replaces it:

**2.1 The loop was expensive and front-loaded.** The first full review raised only ~17 % of what the loop
eventually raised, later rounds were the same sampler drawing again, the median ticket took 7.5 rounds and the
loop was a fifth of all spend. -> No reviewer sessions at all; `review_round` is gone from the contracts.

**2.2 A self-check is cheap and catches the obvious.** -> The implement prompt ends with Claude walking plan.md's
acceptance criteria and stating done or not done for each (`self_check`); informational, never proof.

**2.3 Tests and reading code are not evidence the thing works.** The predecessor's regression table is full of
"proven" criteria that were not (a recording with no audio, tests that pass on the base). -> The `live_check` stage:
Claude starts the live changed app or script, drives it (headless browser, CLI, curl, device deploy, game autodrive,
per the e2e-ground-truth skill) and reports what it saw per criterion; screenshots optional, no video.

**2.4 Cheap checks run on the server, not in a model.** -> Checks stage: done_check, tests, linters, pre-commit via
`capped.sh`; red goes back to Implement at most twice, then `failed`. The tails of the live-check report and the
checks are what `close_task` receives as evidence.

**2.5 A loop needs a cap.** Wherever an automatic retry exists (checks fix attempts, live-check fixes) it is
bounded by a count; exhausting it ends in Needs you, never in another silent loop.

## 3. UI and state lessons from the regression table

**3.1 Stale tabs.** A shipped UI update left open tabs running old code. -> Build id in `index.html` and `/version`;
the page polls and reloads on change.

**3.2 Polling windows.** "Within 3 minutes" updates were reported as bugs. -> SSE for live state; polls only for the
board with a visible refresh time; every wait of 1 s or more names what it waits on.

**3.3 A waiting block shown as running.** A task waiting on an external condition showed a spinner among tasks that
did work, so the board lied. -> `queued`, `paused_limit` and `needs_you` are distinct statuses in distinct columns.

**3.4 Offered actions that cannot work.** "Retry" shown for a block no retry could clear; "retries by itself" shown
when it did not. -> Actions are computed on the server with `enabled` and a mandatory `reason`.

**3.5 State overwritten by a slower writer.** A routine sweep read stale state and overwrote a fresh result; a limit
elsewhere overwrote a real stop. -> state.json is written atomically under flock and every update is
read-modify-write with a precedence rule (a stop with an `error` is never replaced by `paused_limit`).

**3.6 Writes that went out twice.** A second push, a second comment, a status move when the target was already
there. -> Ship records `ship.commit/pushed_at/closed_at` and checks the remote and the note's current status first;
each outward step is skipped when already done.

**3.7 Conflicts and dropped connections.** A conflict found at merge time did not stop the merge; one dropped
connection ended a watch with a misleading message. -> Ship rebases and re-runs the checks before pushing, and any
network failure is reported as that failure (`run_failed`), not as "nothing to do".

**3.8 Checks narrower than the repo's own rules.** Running only the test command missed lint and convention errors the
repo's docs already stated. -> Checks stage runs the done_check, the repo's test command, its linters and its
pre-commit, discovered from the repo's CLAUDE.md `## Commands`, all through `capped.sh`.

**3.9 Evidence must be checkable.** A criterion about audio was "proven" by a recording with no audio track. -> Each
criterion needs evidence of a kind the pipeline can validate (command exit code and output, or a screenshot that
exists and is non-empty); criteria it cannot check become a human item in Needs you, naming the exact check.

**3.10 Skip decisions bind to a head.** A "go on without this" click applied to one commit, so the next commit asked
again. -> Skips, if ever added, are keyed by task, not by head.

**3.11 Configuration the user had to type.** Repo paths were hand-edited into a config file before anything worked.
-> The repo set comes from the todo notes' `repo` field and `~/src`; first run needs no config file.

## 4. Avoid list

| Avoid | Why it hurt | What todoImplementer does |
|---|---|---|
| Status-badge combinatorics | dozens of flag combinations, each with its own bug | one status, ten values, server-side |
| Optimistic fake states | UI claimed done before the work was | state changes only from the server's event |
| Retry that cannot pass | the click repeated a doomed step | action disabled with its reason |
| Review loop with no no-progress cap | spend grew with no new findings | no review loop; every retry has a count cap |
| All MCP servers loaded per session | context and tool-list cost on every turn | accepted on purpose: kuhy wants his full setup; cost shown in usage |
| A forge CLI that exits 0 on error | failures read as success | check output and remote state, never only the exit code |
| Hand-editing config on first run | blocked people before any value | derive from notes, `~/src` and the environment |
| Complexity sprawl | hundreds of rows for one UI | 250-line cap, one contract per boundary |
| Uncapped fan-out | many hosts and recorders, each a failure source | local only, three runs, no recording |

## 5. Process lessons

- Bugs are rows first: the table of regressions earned its keep only because every row named a test that was red
  before the fix (`scripts/check_regressions.py` enforces the link).
- Gates are code, not prose: the line cap, the private-value scan and the coverage floor run in `make fast`.
- Tests are hermetic: temp HOME, shims for `claude` and `git push` (a real push fails the test), a fake todo MCP.
- Schemas at every boundary: `state.json` and each `/api` answer are validated by server and web tests alike.
- The human's attention is the scarce resource: automatic first, then one precisely aimed click.
