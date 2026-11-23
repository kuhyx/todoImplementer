# todoImplementer spec

Contract for every part. JSON shapes are in `contracts/*.schema.json` (JSON Schema 2020-12); this file says what
they mean. Lessons from the predecessor are in `DOCS-lessons.md`.

## Decisions (kuhy, final)

- **Q1** Name `todoImplementer`; private GitHub repo `kuhyx/todoImplementer`, created only when told.
- **Q2** The todo app is the only task store, through its MCP (`http://127.0.0.1:8735/mcp`, Streamable HTTP, bearer
  token in `~/.config/todo-mcp/tokens`). Tools: add_task, list_tasks(repo?, status?), get_task, update_task,
  close_task(id, evidence), search_tasks; ids are 8-char prefixes. Never read BACKLOG.md; never edit `~/src/todo`.
  Run state (assignee, stage) lives in `~/.cache/todoImplementer/<item id>/` (`$TODOIMPL_HOME` overrides the root).
- **Q3** Loopback server 127.0.0.1:8786 as a `systemctl --user` unit, linked from the control-panel manifest, and
  published at `https://agents.kuhy.duckdns.org` by extending `publish_caddy_site.sh`.
- **Q4** Stages: Spec (only if the note lacks done/verify/done_check) -> Plan (`plan.md` with acceptance criteria)
  -> Implement (git worktree per task; its prompt ends with a self-check: Claude walks plan.md's criteria and states
  done / not done for each) -> Live check (Claude runs the LIVE changed app or script and reports what it saw per
  criterion; tests and reading code do not count) -> Checks (the server runs done_check, tests, pre-commit via
  `capped.sh`) -> Gate (kuhy) -> Ship (rebase on origin/main, recheck, commit with `Todo: <id8>` trailer, push,
  close_task with the live-check report and the checks' output tails as evidence, remove worktree). CHANGE
  2026-11-05: no AI review loop and no verify/proof stage, ever. Screenshots are allowed, video is not. Excluded for good, never added to any backlog: video
  recording, remote hosts, meetings, Windows/macOS.
  Live check verdict (kuhy, 2026-11-07; a `(kuhy)` criterion blocks it, DOCS-asks.md): one done criterion is enough: the run goes on to Checks and the open ones
  become one follow-up note (retried on a timer, never Needs you, no turn spent). Every start judges failed live checks
  again from their stored report, so a rule change reaches old runs. Least effort lists question cards first.
- **Q5** Automatic: everything up to and including Ship. kuhy's clicks: Spec OK, Start, Cancel, lesson approval.
  CHANGE 2026-11-19 (T2060): no Ship click, no Ready to ship column: a green card ships itself (DOCS-landing.md,
  "Ship by itself"); the 2026-11-08 Auto-ship tick is gone. CHANGE 2026-11-09: sessions land their own work
  (DOCS-landing.md). Never force-push; never edit kuhy's checkout.
- **Q6** Headless `claude -p` with stream-json, resume by session id, live feed (SSE), a Send-to-Claude box, a "copy
  resume command" button (`cd <worktree> && claude --resume <id>`); never open a terminal on :0.
- **Q7** No cap on concurrent runs (kuhy, 2026-11-05: the tool exists to run many at once): every Start drives at once. Opus implements (cheap notes: Opus manager, `DOCS-tiers.md`), Sonnet specs, Haiku classifies. A plan limit pauses
  all runs and resumes at `resetsAt`, or goes on the free API credits (`DOCS-credits.md`); never overage. Cost per task.
- **Q8** Lessons go to `~/.claude/skills/*` via `skill_lesson.py add`, only after kuhy approves a lesson drafted on
  each gate rejection. The UI shows which skills a run loaded. No skills inside this repo.
- **Q9** Board columns Backlog / Running / Needs you / Done (a shipping card is in Running); a card per task, grouped or filtered by
  repo; click opens a side drawer (live feed, plan, diff, live-check report, checks, actions). Tokens from `@kuhyx/web-ui` and the
  unified-design-system warm palette; no invented colours; looks unlike the predecessor's list UI.
- **Q10** Assignee `human` or `claude`. A note with no `repo` is in kuhy's Yours lane. Claude can hand a task to kuhy,
  naming exactly what it needs (needs kind `handed_to_you`).
- **Q11** Done = open the page, see every open note grouped by repo, start at least 3, they run in parallel worktrees with live
  feeds, each ships itself with plan + a live-check report + green checks: it pushes and closes.
- **Q12/Q15** Public without VPN: per-device cookie from a pairing QR (no OAuth client; `DOCS-phone.md`);
  the server binds 127.0.0.1, checks Origin and a CSRF token on every POST; Caddy rate limit.
  Secrets in `~/.config/todoImplementer/` mode 0600. A handoff script covers the OAuth client (no API exists).
- **Q13** Full control from a phone; layout works at 390x844.
- **Q14** The public host is `agents.kuhy.duckdns.org`.
- **Q16** Repo rules: 250 lines per file; every bug is a row in `tests/regressions/*.md` plus a test tagged with its id
  that is red first; hermetic tests (temp HOME; shims for `claude`, `git push`, the todo MCP); JSON Schemas in
  `contracts/` validated by server and web tests; ONE server-computed status per task; actions only when they can
  succeed; a change shows within 100 ms, a wait of 1 s or more shows a loader naming what it waits on.
- **Q17** Spec: Claude posts open questions as cards (`Q<n>` title, body, recommended answer); kuhy answers; the "Spec
  OK" click starts Plan.

## Stage machine

`stage` is written only by the runner into state.json. `spec_wait`, `failed`, `paused_limit` and `cancelled` are
resting stages; the rest are work stages. "auto" = no click; "click" = kuhy. Closing runs: `DOCS-autoclose.md`.

| From | To | Trigger | Kind |
|---|---|---|---|
| (no run) | spec | Start, note lacks done_check | click |
| (no run) | plan | Start, note has done_check | click |
| spec | spec_wait | reply carries open questions or tag Q/A | auto |
| spec_wait | spec | spec-answers saved, Claude re-checks | click |
| spec_wait | plan | spec-ok, every question answered | click |
| plan | implement | plan.md written with acceptance criteria | auto |
| implement | live_check | implementer's turn ends with tag D and its self-check | auto |
| live_check | checks | report written (what was run, what was seen per criterion) | auto |
| live_check | implement | report says a criterion is not met, fix attempt left (max 1) | auto |
| checks | shipping | all checks green (no rest at `gate` since T2060) | auto |
| checks | implement | checks red, fix attempt left (max 2) | auto |
| checks | failed | checks still red after the attempts | auto |
| shipping | shipped | push + close_task done (no diff with auto_ship: close_task only) | auto |
| shipping | failed | rebase conflict, red recheck, push refused | auto |
| any work stage | paused_limit | plan limit seen; `resume_at` = resetsAt | auto |
| paused_limit | stage before | `resume_at` passed | auto |
| any non-final (final = shipped, closed, cancelled, done_manually) | cancelled | cancel (stops the session, keeps the run dir) | click |
| failed, cancelled | plan/spec | start again | click |
| live_check or checks with `error`, or failed | implement | send (kuhy's note; error cleared) | click |

A work stage reply ends with a status tag line: `Q:` or `A:` makes the task Needs you (stored in `last_tag`), `D:`
continues, `R:` means still running. Implement prompts begin with `override` after Spec OK so the spec gate of
kuhy's hooks does not turn them into a grilling round. Spawned sessions set `CLAUDE_AUTO_CONTINUE=0`.

## Single status per task

`board.status.compute(task, run, live, limit_until)` returns exactly one; the page only displays it. Order of rules,
first match wins:

| # | Rule | Status | Column |
|---|---|---|---|
| 1 | todo status done, or stage shipped or closed | done | done |
| 1a | stage done_manually (the Done manually click, or the note was marked done in the todo app: `DOCS-manual.md`) | done_manually | done |
| 1b | todo status abandoned, or stage cancelled (Cancel abandons the note when no other section is open) | cancelled | done |
| 2 | no run and repo null | yours | backlog |
| 3 | no run | backlog | backlog |
| 6 | stage failed, or `error` set, or `last_tag` in Q/A while not live, or stage spec_wait | needs_you | needs_you |
| 7 | stage shipping (or a legacy `gate`) | shipping | running |
| 8 | stage paused_limit, or limit active and not live | paused_limit | running |
| 9 | work stage and live | working | running |
| 10 | work stage, not live | queued | running |

`needs.kind` explains rule 6: spec_questions (unanswered cards), spec_ok (all answered), claude_question (tag Q),
claude_action (tag A, names the action), permission (below), checks_failed, run_failed
(crash, push refused), handed_to_you (a run whose assignee Claude switched to human, with a stated need). The card's `current` line says
what is happening ("live_check", "waiting to start"); `stage` is never turned into extra badges.

## Actions

Server-computed per card as `{id, label, enabled, reason}`; a disabled action always carries its reason; the page never
decides. `start` enabled when status is backlog or cancelled, the note has a repo, and no usage limit holds (free
credits taking over is no hold; a MANUAL WORK REQUIRED title is human work: disabled; board `slots` is just `{used}`);
`spec-answers` when a question is open; `spec-ok` when every question is answered; `send` while a session exists and the
stage is not final (`shipped`, `closed`, `cancelled`, `done_manually`), including `failed` and stalled runs but never a closing run; `cancel` on any status whose stage is not final; `lesson-approve`
when a lesson is drafted; `copy-resume` (carries `value`, no POST) when a session id exists; `go`, `copy-fix` (carries `value`, no POST) and `rerun` on a permission block (below); `wont` on Backlog, Cancelled, Yours and Needs you (DOCS-repotask.md); `done-manually` on every status but the two Done ones, with confirm, disabled while shipping (DOCS-manual.md).
No `ship`, `close` or `auto_ship` option is offered (T2060); Start, Retry and Hand back send `{}`.

## Permission blocks heal themselves

kuhy, 2026-11-06: a turn stopped by a permission, not by a real question, is never left for kuhy first. The stream
parser collects the final `result`'s `permission_denials` and hook errors; a denial is terminal when no tool call
succeeded after it, and only terminal denials of a turn that did not end on `D:` or `Q:` count.

1. Auto-allow. `runner/permissions.py` maps each denial to a narrow rule: Bash gets `Bash(<first 2-3 plain words>:*)`
   per simple command (exact for `python -c` code), Edit/Write `Edit(//<abs path>)`, Read, the exact MCP tool name,
   `WebFetch(domain:)`. Rules are learned in `$TODOIMPL_HOME/allow.json` (global, per repo, per task), passed as
   `--allowedTools`, logged as an activity event, and the same stage reruns with a resume prompt, 2 times at most.
2. Never-list, only while no session policy file exists: git push (a hard deny, not a gap), sudo, chattr, system
   `systemctl`, `rm -r` outside the worktree and run dir, curl-to-shell, `~/.claude/settings*` and hooks, writes
   outside the worktree and run dir, `.git/`, secrets, MCP tools that send, delete or update. Hook blocks and
   "cannot be auto-allowed" refusals are never allowed by a rule.
3. Needs you, kind `permission`: `needs.command` is a one-liner that works from any directory (`cd <abs> && ...` for a
   blocked Bash call, a `jq` command on `~/.claude/settings.json` for a rule), kept in `extra["permission"]`. `go`
   runs it as kuhy (55 s cap, no terminal; disabled with "needs a terminal: copy it" for sudo, ssh, pacman...),
   puts exit code and output tail in the feed and reruns the failed stage on exit 0. `copy-fix` copies it; `rerun`
   ("Done, rerun") reruns after kuhy ran it in a terminal. A card with no command (a hook block) offers Retry.
4. Sensitive files. Claude Code's own "sensitive file" refusal (`decision_reason_type: safetyCheck`) is not lifted by
   the permission mode, and `disableAllHooks` also kills the PermissionRequest hook that could lift it. Inside the
   worktree it is answered with advice and a rerun: write the file with a Bash command (patch or python). Under a
   session policy the implement prompts always carry that advice.
5. Session policy `~/.config/todoImplementer/session-policy.json` (`$TODOIMPL_POLICY`): `permission_mode` (default
   `acceptEdits`), `add_dirs` (default none, `~` expanded), `disable_hooks` (default false; passes
   `--settings '{"disableAllHooks":true}'` to board sessions only), `deny` (null or missing = the built-in
   `git push` list, `[]` = none; the read-only role keeps its Edit/Write deny). A missing file keeps today's
   behaviour; an invalid one is ignored with a feed warning; a valid one lifts the never-list in item 2.

## Endpoints

GET `/version`, `/pair`, `/api/board`, `/api/task/<item-id>`, `/api/usage`, `/api/live?id=<item-id>` (SSE); POST
`/api/task/<item-id>/{start,spec-answers,spec-ok,send,ship,close,cancel,lesson-approve,go,rerun,wont,done-manually}`, `/api/settings/credits-fallback`, `/api/pair`. Shapes: `version`, `pair`, `board`,
`task`, `usage`, `live`, `requests` (one def per POST), `response` (all POSTs). Cross-file refs use each schema's
`$id` (`https://todoimplementer.local/contracts/<file>`); load every file into one registry
(`scripts/contract_lib.py` in Python, `ajv.addSchema` in web). POSTs need `X-Todoimpl-Token` and a same-origin
`Origin`. The server stamps the build id into `index.html` and `/version`; the page reloads when it changes.

## Cards are items

A note's `## ` sections are its items (`todo_mcp/items.py`); a note without sections is one item. A repo is ONE card
(1 repo = 1 task): its open sections are the parts of one run, id `<repo hash8>-0` (`DOCS-repotask.md`); a section card
`<note id8>-<index>` lasts only for a run begun before. Closing an item marks `## [x]` + `closed:`; the note closes last.

## Run-dir layout

`<root>/<item id>/` (item id = `<note id8>-<index>`, below) with root `$TODOIMPL_HOME` or `~/.cache/todoImplementer`:

- `state.json` atomic (tmp + os.replace under flock); `plan.md`; `questions.json` (spec cards)
- `<role>-<epoch>.stream.jsonl` raw stream-json of each turn, in the run dir itself; `<role>-<epoch>.result.json`
  its `result` event, written after claude exits (a stream without it is a killed turn: resume it with a kill note);
  `.exit.json` (code, written by the turn host), `.stderr.log`, `.fed` (feed offset), and `turn.pid` (see Turns)
- `evidence/` check output logs and live-check screenshots (`live_check.shots` paths are relative to the run dir)
- `logs/checks-<epoch>.log`, `live_check.md` (the report), `self_check.json`
- `limit-until` (one epoch; shared in the root), `credits-exhausted`, `overage-alert.json`, `<stem>.route`
- the worktree is `<root>/<item id>/wt` on branch `todo/<item id>`; Ship removes it. A closing run has none.

## Sessions

Every work session (spec, plan, implement, live_check, manager) runs with kuhy's full setup: his `~/.claude` rules,
skills, hooks, agents and the target repo's project memory. MCP is lean, not his full set (T1986, `DOCS-turns.md`):
only the Haiku one-shots (merge classifier, lesson drafter) also drop settings, hooks and tools (`DOCS-turns.md`). without a session policy `git push` is denied with `--disallowedTools`; with one they land their own work (DOCS-landing.md). A resumed
session's `total_cost_usd` is cumulative, so the runner stores the latest value rather than adding turns. Turn model, effort, live-check role, time limit, retry cap: `DOCS-turns.md`.

A Ship failure (conflict, red recheck, push refused) sets stage `failed` with `error`; the Send click reopens the
task at `implement`, keeping the session. Sessions get `CLAUDE_AUTO_CONTINUE=0`.

## Turns outlive the server (T1817)

Why: kuhy edits, restarts and deploys this server while sessions run, so nothing a turn needs may live in the
server. Each turn is `python -m todoimpl.runner.turnhost <run_dir> <stem>`, launched as its own transient unit
(`systemd-run --user --collect`, `KillMode=control-group`; `TODOIMPL_TURN_LAUNCH=direct` is a detached child, for
tests only). A transient unit does not inherit the server's env (probed: no `CLAUDE_*` arrives), so argv, cwd and
env travel in `<stem>.invoke.json` (mode 0600, deleted by the host). The host runs claude in its own session with
stdout going straight into `<stem>.stream.jsonl` (a file, not a pipe: no reader has to exist), records
`{unit, pid, start, stem, role, host_pid}` in `turn.pid`, and writes `<stem>.exit.json` when claude exits. No shell
wrapper: bash reads a script as it runs, so an edit would corrupt a live turn; the host imports everything up front.

The server only tails the stream (50 ms polls) and finishes when the exit record exists and the stream is read.
After a restart `Engine.recover` queues every run with a recorded turn, and `run_turn` adopts it before anything
else: a live turn is re-read (the feed is not replayed past `.fed`), a finished one is consumed from its files, a
host that is gone without an exit record is a lost turn (error line, then the usual "killed" resume), and a
record without a stem (pipe-spawned by the old server) is reaped once. A turn of another role than the one asked
for is waited for, charged, its result dropped, then the asked turn runs. Cost and session are applied once:
`extra.consumed_turn` is saved in the same write. The one window left is a crash after that save and before the
stage saves: the stage then reruns its turn (cost not doubled). Cancel stops the unit (`systemctl --user stop`;
direct launch: the recorded process group); `Engine.close` makes drives let go without signalling a turn.
`scripts/deploy.sh` checks `/version` reports `git rev-parse --short HEAD`. It restarts the unit only when the board
serves another build, is not active, the preview unit is, or a unit file changed; `--restart` forces it (T2513).

## Phone criteria test themselves (kuhy, 2026-11-08)

A board session never needs kuhy at the phone. Criteria that need the Pixel are built once and tried on the
emulator, then staged in `phone_ready.json` (`A: phone:` rests the card until the Pixel shows). With the Pixel in,
the live check runs on the session's own slot, in parallel with other runs: `phone_slot.sh acquire` (private
`com.kuhy.slotN`), `phone_deploy.sh --slot` (sandbox RTDB namespace `SYNC_NAMESPACE`, no icon, muted), steps on its
own virtual display via `phone_vd.sh`, `phone_slot.sh release`. Never over kuhy's app, never the real screen.
Feel/audio criteria are `[~] skipped: needs a human sense` and never block; the note can ask for an `after ship` row.
Runner side (`runner/phone.py`, `hands_nudge`): when a live-check turn ends on an `A:` asking kuhy to tap, open,
look, plug, pause or feel, ONE runner nudge turn tells Claude to do it on its slot; a second ask rests as Needs you
with the ask text. An unattached `A: phone:` (the cable wait) and an attached one (a lost phone) are never nudged.
The server also checks `adb devices` itself (kuhy, 2026-11-19): a turn that ends `A: phone:` with the Pixel already
listed as `device` (emulators beside it do not matter) goes straight back to the session on the attached prompt,
once; a Send to a waiting card does the same, and the watcher (5 s) resumes any card that waits while the Pixel
shows. `phone_ready.json` is applied in implement and live-check turns only: a spec or plan turn never re-parks.

## Token usage (CHANGE 4)

The token-usage tracker lives in this repo, no longer in its three old homes. Layout: `server/todoimpl/tokens/` (ingest, store, analysis, audit, prices), `server/todoimpl/tokens_api/` (routes under
`/api/tokens/*`, registered by the http layer), `mcp/` (stdio MCP server with the old tool names, calling `127.0.0.1:8786/api/tokens`), and the web pages `web/src/pages/usage*.astro` with
`web/src/usage/`. The SQLite DB stays at `~/data/token-dashboard/tokens.sqlite` with no migration; tests use temp DBs only and never touch the real one. Ingest runs as `python -m
todoimpl.tokens.ingest --budget 45` (a unit file in `deploy/`, not installed). The join: a run's session ids give cost per item, repo and stage. The old code is removed only after kuhy confirms parity
(the new API's answers equal the old `:8760/api/tokens` answers on the real DB, read-only, for the main endpoints).

## Autonomy metrics (CHANGE 5)

`GET /api/usage` carries `autonomy` (`contracts/autonomy.schema.json`), shown on the usage page tab Autonomy. Four metrics, each with value, target, direction and a per-ISO-week series; Ship is not an
intervention.

- `done_unassisted` (up, target 100 %): finished cards (shipping, Done) with no recorded intervention.
- `permission_asks` (down, 0): A: turns whose line asks for a permission or approval (`usage/asks.py`).
- `questions_asked` (down, 0): spec question cards plus the questions of free Q: turns.
- `criteria_failed` (down, 0): open plus deferred criteria of a settled live check (`extra.partial`, else the report).

Interventions are appended to `<run dir>/interventions.jsonl` by the service when an action is accepted (`start`, `retry`, `spec_answers`, `spec_ok`, `send`, `cancel`; any new kuhy click, such as
`go`, calls `usage.interventions.record`). Cards without that file are backfilled from answers, Spec OK, Send notes and Q:/A: turns; restarts, cancels and `go` clicks before the record cannot be
recovered.

## Manual sessions (CHANGE 6)

The Sessions tab of control-panel lives here as the page `/sessions` (`web/src/pages/sessions.astro`, `web/src/sessions/`; icon link on the board next to the usage link), backend `server/todoimpl/sessions/` plus `http/sessions.py`, contract `contracts/sessions.schema.json`: kuhy's hand-started Claude Code sessions (headless `sdk-cli`/`sdk-py` runs hidden), status from the reply's tag line, resume (terminator via `systemd-run`, a copy button on a phone), mark done (shared `~/.claude/session-status.json`) and delete (to `~/.claude/projects-trash`); the POSTs sit behind the Ship guard (Origin + CSRF). Details, parity and decisions: `DOCS-sessions.md`.
