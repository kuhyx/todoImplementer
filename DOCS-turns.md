# Turns: model, effort, session, time limit, retries

Claude-usage rules of one turn (kuhy's yardstick: claude.dev, which Claude model to build with, 2026-11-09: Opus medium by default, verify and report work on Sonnet, classification on Haiku; when a model falls short, first a way to check its work, then more effort, then a bigger model; code, not a model, picks the model). Sessions and the full-setup rule: `DOCS-spec.md`, "Sessions". Code: `server/todoimpl/runner/{claude,prompting,turn,turnhost,launch,retry,oneshot}.py`.

The Haiku one-shots (merge classifier, lesson drafter) are minimal: `runner/oneshot.py` gives them no settings
sources (so no hooks, plugins or rules), MCP servers, skills or tools, `--effort low` and a scratch cwd, reads both
shapes of `--output-format json` (one object, or the event array of claude 2.1), and appends cost and tokens to
`<root>/oneshot-usage.jsonl`, which `/api/usage` adds to `cost.total_usd` (`cost.oneshot_usd`).

Per-turn knobs (`runner/claude.py`): model by role (`ROLE_MODELS`), `--effort` by role (`ROLE_EFFORT`: medium, the
classifier low) and high for a fix turn; the credit spec passes it to the SDK. The **live check is its own role**
`live_check` (Sonnet, medium): verify-and-report work in a fresh session seeded from `handoff_summary` (plan text in
the prompt, not twice), so it never resumes the Opus transcript and pays no cache write on it. Its session is dropped
whenever the implementer worked since (entering from `implement`); the checklist redo, the phone nudge and an `R:`
continue resume it. A resumed session already holds plan.md: its prompt names the path, a new one inlines the text
(`Situation` `resume`, `runner/prompting.py`). `result.json` records `model`, `wanted_model` and `effort`; when the
credits route runs a role on a lesser model than it wanted (every credit turn runs the `credits_model` setting, default Opus 5.5; a Sonnet role on Opus is no hold) the feed says so and
`state.extra.credit_downgrade[role]` holds `{wanted, ran}`.

A turn has a wall-clock limit: `$TODOIMPL_TURN_TIMEOUT` seconds (default 4 h, above a manager round with coaching).
The limit travels in `<stem>.invoke.json`, so the turn host enforces it across a server restart: SIGTERM, then
SIGKILL, `timeout: true` in the exit record, the reason in the stderr log; the run then retries like a crash.
A turn idle after its result is ended (T1991, `runner/idle.py`) once its stream was silent for 10 min and no shell
was seen below claude (looked for every 1 s) for the last 60 s. The 60 s let claude take a finished job's notice
(it takes 0.1 s, at most 5.5 s over 237 notices); without them a job that ran past 10 min had claude stopped the
instant its shell left, and the notice was lost (T2194). The next turn starts within 1 s of the stop.
A server-side API error (5xx, overloaded) is retried at most `retry.MAX_API_RETRIES` (12) times on the ladder of
`DOCS-resilience.md` (about 4 h); after that the run rests in `failed` with "Gave up after N automatic retries:
<reason>". Waits that kuhy's rules keep unbounded stay so: a lost connection (an outage), the todo app and the live
follow-up note (`retry.later` is uncapped; DOCS-resilience, DOCS-spec Q4). A bare `API Error` or `timed out` is no
longer transient: it takes the crash path (3 tries, then Needs you).

Not changed on purpose: Sonnet for spec and plan (`tokens/ab.py` compares subagent arms only and holds no data for these board roles); every role on credits runs the `credits_model` setting (Opus 5.5 since 2026-11-15; Sonnet before, kuhy 2026-11-08).

## kuhy's model pick (T2215-T2220)

kuhy can pin a card to a model (2026-11-19, "run it on claude fable 5.2"): a Send-to-Claude note that is a whole
model command, or the task detail's model picker (`POST /api/task/<id>/model {model}`, relay kind `task_model`).
Code: `server/todoimpl/modelpick.py` (names, plain regex, no LLM), `runner/modelswitch.py`.

- Names: Fable 5.2 `claude-fable-5-2`, Opus 5.5 `claude-opus-5-5`, Sonnet 5.5 `claude-sonnet-5-5`, Haiku 5.5
  `claude-haiku-5-5`, with or without `claude` and the version ("fable", "rerun on opus", "use sonnet 5.5", "on
  haiku"); `default` drops the pin. A note with any other words or version is an ordinary note, except one that
  starts with a run / rerun / switch command and a separator ("run it on fable 5.2. Try bolder logos", T2221): it
  pins the model and the rest reaches the rerun session as kuhy's note.
- The pin (`state.extra.model_pin`) wins over the role, tier, research and escalation models and over
  `credits_model` on the credit route, until kuhy names another model or `default`; effort stays the role's.
- The card's current stage runs again on the pick. A live turn is cut and its session resumed with
  `--resume <id> --model <pin>` (claude 2.1.328 switches a resumed session's model; probed 2026-11-19).
- The card shows `model`: the pin, else the model the latest turn ran on (`state.extra.last_model`).

## Three builds at a time

kuhy's order: at most three builds run at once across all board sessions and the board's own checks
(2026-11-21; it was exactly one from 2026-11-11, after ~25 sessions building at once froze the PC; one slot let
heavy builds queue 4-6 deep for minutes). The per-card 10 GiB and board 18 GiB caps (T2405) keep three safe.
Code: `server/todoimpl/runner/buildlock.{py,sh}`; `buildlock.SLOTS` (`$TODOIMPL_BUILD_SLOTS` in tests).

- The lock is `SLOTS` flock files: `$TODOIMPL_HOME/build.lock` (slot 0, the one old wrappers take) and
  `build.lock.1`, `build.lock.2`; each slot's `<lock>.holder` says `<card> (<cmd>) since <t>`, and a waiter
  prints `waiting for build lock held by <holders, joined by +>; <n> ahead` to stderr once, then waits. Nothing
  times the wait out.
- Slots (T2419, T2420): a waiter goes once fewer than `SLOTS` live tickets are ahead of it, then takes the first
  free slot (all busy, from an old wrapper or a hand-held lock: it waits on slot 0). It blocks on the nearest live
  ticket for 2 s at a time (`buildqueue.RECHECK`) and counts again, so any build that ends lets it on.
  `bgwait.waiters` sees a waiter on any slot file or ticket; the stall detail names the longest holder (T2421).
- Arrival order (T2164, `runner/buildqueue.py`, same protocol in the wrapper): a build first takes the next
  ticket `build.queue/<12 digits>` under `build.queue.lock` and flocks it while it waits and builds; it waits
  for its turn as above, then takes a slot lock (an old wrapper or a hand-held lock on `build.lock` still holds
  slot 0). A ticket whose flock is free is dead (killed waiter, reboot) and is removed by whoever meets
  it. A ticket's line: `<pid> <wait|held> <card> (<cmd>) since <t>`; `buildlock.sh --queue` lists them in order.
- A board check keeps its place across a server restart (T2168): its ticket ends in ` board`; dead, it is
  stamped `gone` and kept 5 min (`buildqueue.RESERVE`), passed over by every waiter, and the restarted server's
  same check (card and command) takes it back. Unclaimed after 5 min, the next look removes it.
- No whole scripts (T2165): `buildlock.sh bash x.sh` (any shell, python or node with a script, `-c` or stdin,
  also behind env, nice, timeout, capped.sh; or a script path) never takes the lock: it prints a one-line hint
  and runs the script unlocked with the shims first on PATH, so each heavy tool inside locks itself; the exit
  code is the script's, so a caller (siege's `hold_build_lock`) never breaks. Under a held lock it runs as
  before. Better: run the script plainly; the Bash tool's PATH has the shims; a `systemd-run` job needs
  `-E PATH -E TODOIMPL_BUILD_CARD` (a repo's `scripts/bg.sh` passes PATH). `python -m x` is one tool.
- Hold ceiling (T2166, `runner/holdceiling.py`, a server thread): every 10 s it samples each holding ticket's
  process tree (every slot, T2422); 2 min with no CPU beyond 1 %, no read or write bytes, no new or gone process and none in disk
  sleep, and it sends the wrapper SIGUSR1: the wrapper lets go of the lock and ticket, the tool runs on unkilled,
  and the card (or the run dir the wrapper works in) gets a `system` activity event. The server's own checks
  and a pid that is no buildlock.sh are skipped.
- No touching by hand (T2167): the standing prompt forbids it, and a `flock` guard shim (in
  `buildlock_queue.sh`, sourced by the wrapper) queues it: a blocking flock on build.lock (a path or an fd, as
  phone_deploy's `board_lock_first` holds it for a deploy) takes a ticket and waits its turn, `flock -n` fails
  while anyone is queued, the holder or queue files exit 2, and under a held lock it runs as asked. A Bash deny
  rule would be inert: kuhy's session policy has `deny: []`.
- Every turn gets one-line shims in `$TODOIMPL_HOME/shims` (flutter, dart, gradle, java for `./gradlew`, pnpm,
  npm, yarn, vite, vitest, cargo, go, cmake, ninja, godot, pytest, uv, pre-commit) that run
  `buildlock.sh <tool>`, plus the `flock` guard. `make` is no shim (T2415): a gate step like `make lint` did
  0.04 s of work but queued minutes; each tool its recipes run locks itself, and `uv run <linter>` (the lanes'
  linter list, `buildlock.LINTERS`) and `flutter|dart analyze` skip the lock. A plain make+gcc build runs unlocked. `ensure` deletes a shim
  that left the list, so running sessions drop it at the next turn.
  Never node, npx, uvx, git, python or claude: MCP servers and claude itself use them.
- The shims reach claude's Bash tool through `CLAUDE_ENV_FILE` (`$TODOIMPL_HOME/shims-env/<card>.sh`, sourced
  before every Bash command), not a PATH prefix: kuhy's zshrc puts `~/.local/bin` (flutter, dart, uv, pytest)
  in front of any inherited PATH. MCP servers and hooks keep the plain PATH, so none of them can hold the lock.
- Under a held lock `TODOIMPL_BUILD_LOCK_HELD=1` is set, so nested tools (flutter -> gradle -> java, uv ->
  pytest) run at once. A version or help probe (`--version`, `-version`, `version`, `--help`, `-h`, `-V`, `help` as
  the only argument) and a dev server (`dev`, `serve`, `start`, `preview`, `watch`, also after `run`) skip it.
- Only the wrapper's bash holds the lock fds; the tool runs without them (in the background, so the wrapper hears
  SIGUSR1 and forwards TERM, INT as TERM, and HUP), so a daemon it leaves never keeps the lock.
- The board's checks (`checks.run_capped`: done_check, `make test`, pre-commit, gate steps, autocheck) take
  a lane before their timeout starts (T2186, `runner/lanes.py`). `lanes.classify` calls a command `light` only when
  every part (split on `;`, `&&`, `||`, `|`; `timeout`, `uv run`, `python -m`, `VAR=` peeled) is a known linter
  (ruff, mypy, pyright, shellcheck, shfmt, black, isort, flake8, pylint, bandit, codespell, yamllint, actionlint,
  markdownlint, eslint, prettier, git, plus head/tail/grep/wc/sort/cat as output filters), or `pre-commit` when no
  hook `id`, `name`, `entry` or `language` of the repo's config names a build tool, `build`, `test` or `tests`
  and no repo script an entry runs mentions one. Everything else (make, flutter, uv sync, scripts, `$(...)`,
  subshells, an unreadable config) is `heavy`. A heavy check takes the build lock as above; a light one takes the
  one-slot `$TODOIMPL_HOME/light.lock` (holder in `light.lock.holder`, same wait line), so a check wrongly called
  light costs at most one extra build next to the one build: the 2-slot fallback. Both run under capped.sh.
- Queue and run time are separate (T2185): `run_check` writes one event per check, `check <name>: lane=<heavy|light>
  queue=<s> run=<s> exit=<n|timeout> [behind=<holder>]` (a restart resets the queue part). While a check queues
  the card's `current` reads `⏳🔒 <holder> <HH:MM>` (the idle-turn line below, `bgwait.holder`; a ship step reads
  `shipping: <step> ⏳🔒 ...`), through `stepwatch.Watch` that `Driver.run` installs per drive (umbrella round
  checks copy the context into their pool threads). Of the 212 min the analysis of 2026-11-19 called scheduler
  queueing, 139 min were kuhy's own spec answers and 73 min were checks queued here (T2187); `Engine._take` waits
  only on the usage limit, a retry timer and the per-repo lock (`DOCS-repotask.md`).
- Turn env build tuning (`buildlock.TUNING`): `GRADLE_OPTS` (no daemon, 4 workers, `-Xmx3g`) and
  `CARGO_BUILD_JOBS=4`; no `MAKEFLAGS` (make already runs one job; `-j4` would raise it). The standing prompt says a wait is normal and never to kill a waiting build.
- An idle turn names its wait (T2124, `runner/bgwait.py`): once a turn's result is in and its stream has been
  silent 1 s, the follower looks every 1 s at the live shell jobs below claude. If a waiter on `build.lock` (a
  `->` line of `/proc/locks`) is the card's (below claude, cwd in the card's run dir, or `TODOIMPL_BUILD_CARD`
  in its environ; a `systemd-run` job is no child of claude) the card's line reads `⏳🔒 <holder> <HH:MM>` (the
  holder's card, or its command when the card is `?`, and since when it holds); else `⏳ <job command> <HH:MM>`.
  It sits in `state.extra.waits_for`, is saved and announced as a stage event, and is cleared when the stream
  speaks again and when the turn ends.
- The turn's 4 h clock (`$TODOIMPL_TURN_TIMEOUT`) stands still while its only live work waits on the lock
  (T2270, `runner/turnclock.py`): every 1 s the host checks that the stream did not grow since its last look and
  that `bgwait.scan` finds a waiter on the lock that is the card's (same attribution as the card's line, also a
  `systemd-run` job in the run dir). Then the deadline moves on by that second. The lock path travels in
  `<stem>.invoke.json` (`lock`); a host started by an older server has none and counts every second. A second
  job that works beside a waiting one also stops the clock; other cards' holds are bounded, so the turn is not.
- Not locked on purpose: a job started with `systemd-run` that keeps the user manager's PATH (no shims). It may
  outlive the turn, and a server or watcher there would hold the lock for good; the slice caps its memory. A
  job that passes PATH on (a repo's `scripts/bg.sh` does) takes the lock, with `?` as its card.

## Lean MCP (T1986)

Every turn, plan route and credit route, passes `--strict-mcp-config --mcp-config <json>`, so none of kuhy's user,
project or plugin MCP servers start (about 500 MB per session; 25 sessions froze the PC). The json holds nothing,
except the driver of the repo kind: Flutter adds flutter-web-drive, Godot godot-mcp-runtime (`runner/mcpconf.py`).
The definition comes from `~/.claude.json` (a restored server), else `~/.claude/mcp-parked.json`; a server kuhy
does not have is skipped silently. The board's own tasks need no MCP: sessions tick through the repotask CLI.

## Silent turns: the watchdog (T2195-T2199)

kuhy's rule (2026-11-19): a running card whose last real action (a tool call or result, model output) is over
1 min old is suspicious; over 5 min it is fixed at once. A `tool_progress` heartbeat (every 30 s while a tool
runs) and a rate-limit notice are no action; nothing makes a session look alive, and no bare timeout kills a
healthy wait. Code: `runner/watchdog.py` (the follower's side), `runner/deadwait.py` and `runner/deadrules.py`.

- The follower keeps the time of the last real line in `<stem>.real` (a deploy or restart keeps the count).
  Past 1 min it judges the turn's jobs every 5 s: each shell below claude with its processes, and each of the
  card's transient units beside its turn unit in `todoimpl.slice` (`bgwait.mine`: cwd in the run dir or
  `TODOIMPL_BUILD_CARD`). A handful of /proc and cgroup reads; no fork.
- Healthy: a place in the build lock's queue, a process (no shell, sleep or poll tool) whose CPU rose since
  the last look, or an event wait (`gh run watch`, `systemd-run --wait`, `inotifywait`, a blocking `flock`).
- Dead: (a) `pgrep -f <pattern>` whose pattern matches no command line but the loop's own and its
  ancestors' (kartka, 22 min on a card already shipped); (b) no CPU for 2 min with every process asleep in a
  pipe read, a futex or a wait for a child (b11.sh, a background job inside `$(...)`, 21 min holding the
  build lock); (c) it names another card that is done, or whose turn is gone and that is not shipping.
  Anything else is unknown.
- The card's line (`state.extra.silent`, server-computed) gains the age in minutes past 1 min, and the job's
  command when no T2124 wait names it: `⏳ <job> 3m`. Past 5 min, `🚨` marks a card with no healthy job and
  `💀` a dead one.
- Past 5 min a dead job is stopped once: its unit (`systemctl --user stop`), else its processes (SIGTERM, only
  those whose start time is still the judged one). The reason goes to the job's stderr (the tool's output,
  read when it returns), the card's feed (an error line) and the inbox (the next turn, as Send to Claude).
- The standing prompt carries the wait rules (`standing.WAITS`): event waits, no self-matching `pgrep -f`, no
  background job inside `$(...)`, no `flock -n` polling or when_free.sh, no wait on another card, no periodic
  "still waiting" output. The self-resume note (T2104) asks for one event wait, no sleep loop.

## Context cap (T2363-T2369)

kuhy's order (2026-11-20, after sessions reached 1.22 M tokens and $212 of spend sat above 300 k): a board session
never grows past `$TODOIMPL_CTX_CAP` tokens (default 300000, `0` = off). Code: `runner/ctxcap.py`; the hook is
`StreamParser.on_context`, set in `turn._consume` for both routes (plan CLI and credit SDK print the same stream).

- Meter: each main-thread assistant event gives input + cache creation + cache read tokens; an event with a
  `parent_tool_use_id` (a subagent) and output tokens are not counted. It reads each turn's own stream, so a session
  that was already running at deploy is cut on its first event over the cap. A context at the cap counts.
- At the cap the turn is stopped through the normal stop (`handle.stop`) and the same stage goes on at once with the
  role's session dropped: the prompt is the handoff summary (`session.handoff_summary`, built from files) plus a
  `(runner)` line: the previous session was stopped at the context cap, uncommitted work may sit in the worktree,
  check `git status` and `git log`. The seed stays on the role until one of its turns finishes.
- Not a failure: `ctxcap.mark` and `go_on` run before the failure path, so `retries`, `crash_retries` and
  `kill_retries` stay as they were, no backoff is added and the card never rests on kuhy. The cut turn's empty
  reply does not replace `last_reply`.
- State: `sessions[role].context_tokens` (latest main-thread context of its last turn), top-level `ctx_reseeds`
  (role -> cuts), and `context_tokens` in each turn's `result.json`. While a role's seed is pending,
  `ctx_fresh[role]` = `{tokens, cap, streak}`; `ctx_hit` only lives between the stop and `mark`. No feed line, no
  banner, no notification; the journal has one `context cap:` line per cut.
- Loop guard: a role cut `MAX_STREAK` (8) times in a row without a finished turn is left alone until one finishes
  (a cap below a fresh session's own start would otherwise respawn for ever).
