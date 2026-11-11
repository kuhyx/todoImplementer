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
credits route runs a role on Sonnet that wanted more (kuhy's rule, 2026-11-08) the feed says so and
`state.extra.credit_downgrade[role]` holds `{wanted, ran}`.

A turn has a wall-clock limit: `$TODOIMPL_TURN_TIMEOUT` seconds (default 4 h, above a manager round with coaching).
The limit travels in `<stem>.invoke.json`, so the turn host enforces it across a server restart: SIGTERM, then
SIGKILL, `timeout: true` in the exit record, the reason in the stderr log; the run then retries like a crash.
A server-side API error (5xx, overloaded) is retried at most `retry.MAX_API_RETRIES` (12) times on the ladder of
`DOCS-resilience.md` (about 4 h); after that the run rests in `failed` with "Gave up after N automatic retries:
<reason>". Waits that kuhy's rules keep unbounded stay so: a lost connection (an outage), the todo app and the live
follow-up note (`retry.later` is uncapped; DOCS-resilience, DOCS-spec Q4). A bare `API Error` or `timed out` is no
longer transient: it takes the crash path (3 tries, then Needs you).

Not changed on purpose: Sonnet for spec and plan (`tokens/ab.py` compares subagent arms only and holds no data for these board roles); every role on credits is Sonnet (kuhy, 2026-11-08).

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
  the same lock before their timeout starts.
- Turn env build tuning (`buildlock.TUNING`): `GRADLE_OPTS` (no daemon, 4 workers, `-Xmx3g`) and
  `CARGO_BUILD_JOBS=4`; no `MAKEFLAGS` (make already runs one job; `-j4` would raise it). The standing prompt says a wait is normal and never to kill a waiting build.
- Not locked on purpose: a job started with `systemd-run` (it gets the user manager's PATH, no shims). It may
  outlive the turn, and a server or watcher there would hold the lock for good; the slice caps its memory.
