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
A server-side API error (5xx, overloaded) is retried at most `retry.MAX_API_RETRIES` (12) times on the ladder of
`DOCS-resilience.md` (about 4 h); after that the run rests in `failed` with "Gave up after N automatic retries:
<reason>". Waits that kuhy's rules keep unbounded stay so: a lost connection (an outage), the todo app and the live
follow-up note (`retry.later` is uncapped; DOCS-resilience, DOCS-spec Q4). A bare `API Error` or `timed out` is no
longer transient: it takes the crash path (3 tries, then Needs you).

Not changed on purpose: Sonnet for spec and plan (`tokens/ab.py` compares subagent arms only and holds no data for these board roles); every role on credits runs the `credits_model` setting (Opus 5.5 since 2026-11-15; Sonnet before, kuhy 2026-11-08).

## One build at a time

kuhy's order (2026-11-11, after ~25 sessions building at once froze the PC): exactly one build runs at a time
across all board sessions and the board's own checks. Code: `server/todoimpl/runner/buildlock.{py,sh}`.

- The lock is `flock` on `$TODOIMPL_HOME/build.lock`; `build.lock.holder` says `<card> (<cmd>) since <t>`, and a
  waiter prints `waiting for build lock held by ...` to stderr once, then waits. Nothing times the wait out.
- Every turn gets one-line shims in `$TODOIMPL_HOME/shims` (flutter, dart, gradle, java for `./gradlew`, pnpm,
  npm, yarn, vite, vitest, cargo, go, make, cmake, ninja, godot, pytest, uv) that run `buildlock.sh <tool>`.
  Never node, npx, uvx, git, python or claude: MCP servers and claude itself use them.
- The shims reach claude's Bash tool through `CLAUDE_ENV_FILE` (`$TODOIMPL_HOME/shims-env/<card>.sh`, sourced
  before every Bash command), not a PATH prefix: kuhy's zshrc puts `~/.local/bin` (flutter, dart, uv, pytest)
  in front of any inherited PATH. MCP servers and hooks keep the plain PATH, so none of them can hold the lock.
- Under a held lock `TODOIMPL_BUILD_LOCK_HELD=1` is set, so nested tools (flutter -> gradle -> java, make ->
  pytest) run at once. A version or help probe (`--version`, `-version`, `version`, `--help`, `-h`, `help` as
  the only argument) and a dev server (`dev`, `serve`, `start`, `preview`, `watch`, also after `run`) skip it.
- Only the wrapper's bash holds the lock fd; the tool runs without it, so a daemon it leaves never keeps it.
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
- The turn's 4 h clock (`$TODOIMPL_TURN_TIMEOUT`) keeps running while a job waits on the lock. Kept on purpose
  for now: the host would need the same /proc attribution as the follower to pause it, and the waiter is often
  outside its tree. A turn queued behind many builds can therefore time out and retry like a crash.
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
