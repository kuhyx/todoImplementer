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
- **Q5** Automatic: everything up to Gate. Only kuhy's click: Ship, Spec OK, Run on credits (also Start, Cancel,
  lesson approval). CHANGE 2026-11-08: a done_check note started with "Auto-ship when checks pass" ticked (off by
  default, kept by Retry and Hand back) skips the Gate and ships itself; a run with no diff then closes the note
  without a push. Never force-push; never write outside the task worktree and its run dir.
- **Q6** Headless `claude -p` with stream-json, resume by session id, live feed (SSE), a Send-to-Claude box, a "copy
  resume command" button (`cd <worktree> && claude --resume <id>`); never open a terminal on :0.
- **Q7** No cap on concurrent runs (kuhy, 2026-11-05: the tool exists to run many at once): every Start drives at once. Opus implements, Sonnet specs, Haiku classifies. A plan limit pauses
  all runs and resumes at `resetsAt`; overage only on "Run on credits". Per-task dollar cost is shown.
- **Q8** Lessons go to `~/.claude/skills/*` via `skill_lesson.py add`, only after kuhy approves a lesson drafted on
  each gate rejection. The UI shows which skills a run loaded. No skills inside this repo.
- **Q9** Board columns Backlog / Running / Needs you / Ready to ship / Done; a card per task, grouped or filtered by
  repo; click opens a side drawer (live feed, plan, diff, live-check report, checks, actions). Tokens from `@kuhyx/web-ui` and the
  unified-design-system warm palette; no invented colours; looks unlike the predecessor's list UI.
- **Q10** Assignee `human` or `claude`. A note with no `repo` is in kuhy's Yours lane. Claude can hand a task to kuhy,
  naming exactly what it needs (needs kind `handed_to_you`).
- **Q11** Done = open the page, see every open note grouped by repo, start at least 3, they run in parallel worktrees with live
  feeds, each reaches Ready to ship with plan + a live-check report + green checks; Ship pushes and closes.
- **Q12/Q15** Public without VPN: Google sign-in for one account via oauth2-proxy beside the Caddy container
  (`forward_auth`); the server binds 127.0.0.1, checks Origin and a CSRF token on every POST; Caddy rate limit.
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
resting stages; the rest are work stages. "auto" = no click; "click" = kuhy.

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
| live_check | implement | report says a criterion is not met, fix attempt left (max 2) | auto |
| checks | gate | all checks green | auto |
| checks | shipping | all checks green, `auto_ship` set and the note has a done_check | auto |
| checks | implement | checks red, fix attempt left (max 2) | auto |
| checks | failed | checks still red after the attempts | auto |
| gate | shipping | ship | click |
| gate | implement | send (kuhy rejects with a note; lesson drafted) | click |
| shipping | shipped | push + close_task done (auto-ship with no diff: close_task only) | auto |
| shipping | failed | rebase conflict, red recheck, push refused | auto |
| any work stage | paused_limit | plan limit seen; `resume_at` = resetsAt | auto |
| paused_limit | stage before | `resume_at` passed, or credits click | auto / click |
| any non-final (final = shipped, cancelled) | cancelled | cancel (stops the session, keeps the run dir) | click |
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
| 1 | todo status done, or stage shipped | done | done |
| 2 | no run and repo null | yours | backlog |
| 3 | no run | backlog | backlog |
| 4 | stage cancelled | cancelled | backlog |
| 5 | stage gate | ready_to_ship | ready |
| 6 | stage failed, or `error` set, or `last_tag` in Q/A while not live, or stage spec_wait | needs_you | needs_you |
| 7 | stage shipping | shipping | running |
| 8 | stage paused_limit, or limit active and not live | paused_limit | running |
| 9 | work stage and live | working | running |
| 10 | work stage, not live | queued | running |

`needs.kind` explains rule 6: spec_questions (unanswered cards), spec_ok (all answered), claude_question (tag Q),
claude_action (tag A, names the action), permission (below), checks_failed, run_failed
(crash, push refused), handed_to_you (a run whose assignee Claude switched to human, with a stated need). The card's `current` line says
what is happening ("live_check", "waiting to start"); `stage` is never turned into extra badges.

## Actions

Server-computed per card as `{id, label, enabled, reason}`; a disabled action always carries its reason; the page
never decides. `start` enabled when status is backlog or cancelled, the note has a repo, and no usage limit is active
(never disabled for the number of runs; board `slots` is just `{used}`, the running count); `spec-answers` when at least one question is open;
`spec-ok` when every question is answered; `send` while a session exists and the stage is not final (`shipped`, `cancelled`), including `failed` and stalled runs; `ship` only at
Ready to ship; `cancel` on any status whose stage is not final; `credits` only while paused_limit and credits are available;
`lesson-approve` when a lesson is drafted; `copy-resume` (not a POST, carries `value`) when a session id exists;
`go`, `copy-fix` (not a POST, carries `value`) and `rerun` on a permission block (below).
Start/Restart carry `option` `auto_ship` (a checkbox sent as `{auto_ship: bool}`), disabled without a done_check;
Retry and Hand back send `{}` and keep the stored choice.

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

GET `/version`, `/api/board`, `/api/task/<item-id>`, `/api/usage`, `/api/live?id=<item-id>` (SSE); POST
`/api/task/<item-id>/{start,spec-answers,spec-ok,send,ship,cancel,credits,lesson-approve,go,rerun}`. Shapes: `version`, `board`,
`task`, `usage`, `live`, `requests` (one def per POST), `response` (all POSTs). Cross-file refs use each schema's
`$id` (`https://todoimplementer.local/contracts/<file>`); load every file into one registry
(`scripts/contract_lib.py` in Python, `ajv.addSchema` in web). POSTs need `X-Todoimpl-Token` and a same-origin
`Origin`. The server stamps the build id into `index.html` and `/version`; the page reloads when it changes.

## Cards are items

A note's `## ` sections are its items (`todo_mcp/items.py`); a note without sections is one item. A card, a run, its
run dir and every `/api` path use the item id `<note id8>-<index>` (index 0-based, e.g. `c59d2588-0`). Closing an
item marks its section `## [x]` and adds a `closed:` line; the note closes with its last open item.

## Run-dir layout

`<root>/<item id>/` (item id = `<note id8>-<index>`, below) with root `$TODOIMPL_HOME` or `~/.cache/todoImplementer`:

- `state.json` atomic (tmp + os.replace under flock); `plan.md`; `questions.json` (spec cards)
- `<role>-<epoch>.stream.jsonl` raw stream-json of each turn, in the run dir itself; `<role>-<epoch>.result.json`
  its `result` event, written after claude exits (a stream without it is a killed turn: resume it with a kill note)
- `evidence/` check output logs and live-check screenshots (`live_check.shots` paths are relative to the run dir)
- `logs/checks-<epoch>.log`, `live_check.md` (the report), `self_check.json`
- `limit-until` (one epoch; shared in the root, not per task), `limit-credits`
- the worktree is `<root>/<item id>/wt` on branch `todo/<item id>`; Ship removes it

## Sessions

Every work session (spec, plan, implement, live_check) runs with kuhy's full setup: his `~/.claude` rules, skills,
hooks, agents, the target repo's project memory and ALL his user and project MCP servers. There is no
`--strict-mcp-config`, no per-role MCP list and no `--setting-sources` narrowing; only the one-shot Haiku lesson
drafter stays minimal. `git push` is denied to every session with `--disallowedTools`; only Ship (click or auto-ship) pushes. A resumed
session's `total_cost_usd` is cumulative, so the runner stores the latest value rather than adding turns.

A Ship failure (conflict, red recheck, push refused) sets stage `failed` with `error`; the Send click reopens the
task at `implement`, keeping the session. Sessions get `CLAUDE_AUTO_CONTINUE=0`.

## Token usage (CHANGE 4)

The token-usage tracker lives in this repo, no longer in its three old homes. Layout: `server/todoimpl/tokens/`
(ingest, store, analysis, audit, prices), `server/todoimpl/tokens_api/` (routes under `/api/tokens/*`, registered by
the http layer), `mcp/` (stdio MCP server with the old tool names, calling `127.0.0.1:8786/api/tokens`), and the
web pages `web/src/pages/usage*.astro` with `web/src/usage/`. The SQLite DB stays at
`~/data/token-dashboard/tokens.sqlite` with no migration; tests use temp DBs only and never touch the real one.
Ingest runs as `python -m todoimpl.tokens.ingest --budget 45` (a unit file in `deploy/`, not installed). The join:
a run's session ids give cost per item, repo and stage. The old code is removed only after kuhy confirms parity
(the new API's answers equal the old `:8760/api/tokens` answers on the real DB, read-only, for the main endpoints).
