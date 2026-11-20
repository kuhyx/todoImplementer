# App errors become self-fixing tickets

kuhy's rule (2026-11-17): every app error, and every wait the user sees for more than 1 s, is reported by the app,
becomes ONE ticket per identical error, and the board works on it with no questions until it is fixed, shipped and
deployed, when weekly Claude usage is under 80 % or free tokens are still unused. A fix that is pushed but not yet on
his phone reads "wait for phone to connect, then update the app" and finishes by itself when the phone connects.
Code: `server/todoimpl/errors/` (`record`, `adapters`, `sources`, `ledger`, `ticket`, `gate`, `loop`, `settle`,
`marks`), `runner/appfix.py`, `runner/phone_sched.py`. Contract: `contracts/app-error.schema.json`. The apps' side
(reporting) is each app's; kartka's is `~/src/kartka/docs/DOCS-error-reports.md`.

## The contract (`app-error.schema.json`)

A **record** is one identical error or slow wait:

| Field | Meaning |
| --- | --- |
| `app`, `repo` | the app name (`^[a-z0-9][a-z0-9_-]*$`) and the `owner/name` repo that holds the fix |
| `signature` | stable id: the same error always gets the same one (no spaces) |
| `kind` | `crash`, `ui.error`, `perf.slow`, ... |
| `message`, `top_frame?`, `detail?` | masked message, first package frame, free text (durations, route) |
| `count`, `first_seen`, `last_seen` | how often, ISO times |
| `build` | monotonic build of the newest report (Android versionCode); 0 = the source does not know it |
| `version_name?`, `open?` | the build's name; `open` false once the source marks it resolved |

A **report** is `{"version": 1, "errors": [record, ...]}`. The ticket key is `<app>:<signature>`.

## Sources: how an app plugs in

`~/.config/todoImplementer/settings.json` (`$TODOIMPL_SETTINGS`), key `error_sources`: a list of sources
(`contract` `source`): `{app, repo, adapter, path, resolve?, build?}`.

- `adapter` `kartka` maps kartka's `state.json` (`signatures[id]`: type, kinds, sample, count, first, last,
  `resolved`; open = not resolved). kartka's file has no build id today, so `build` is the first of
  `build`/`versionCode` on the entry or its sample, else 0. `perf.*` entries are not uploaded by kartka yet; slow
  waits need that side first.
- `adapter` `contract` reads a report file as is. **Any app plugs in by writing
  `~/.local/state/app-errors/<app>.json`**: every `*.json` there is a contract source with no hooks (set
  `$TODOIMPL_ERROR_STATE_ROOT` to move `~/.local/state`).
- Absent key = the default list: kartka (`~/.local/state/kartka-errors/state.json`, resolve
  `~/src/kartka/tools/errors/run.sh resolve {signature}`, build `git -C {repo_dir} rev-list --count {commit}`,
  because kartka's versionCode is the commit count). `[]` turns the default off.
- `resolve` and `build` are argv lists (no shell). `{signature}`, `{repo_dir}`, `{commit}` are replaced and a leading
  `~/` is the home directory. `resolve` closes the error at its origin; `build` prints the build that holds a pushed
  commit. A broken source file is logged and skipped; the other sources go on.

## The loop (`errors/loop.py`, tick 60 s, started with the server)

Each tick: (1) `settle` (below), (2) each open record gets its ticket, (3) at most ONE card starts.

**Ticket.** One `## ` part of the repo's note, made in-process by `NewTaskService.create` (no HTTP endpoint, no
CSRF). Because kuhy's rule is one card per repo (`DOCS-repotask.md`), the part sits on the repo's card
`<sha1(repo)[:8]>-0`, it is not a card of its own. Title `Fix <app>: <kind> <message, 80 chars> [<sig8>]` (the sig
keeps two errors from sharing a title: the twin refusal). Body, in order: the goal ("Fix this error / bring this
wait under 1 s without breaking existing behaviour. Do not ask kuhy anything; take recommended answers."), a
`done:` line (it spares the Spec stage, which would ask kuhy), error, top frame, detail, build, `Seen: Nx, first,
last`, and last the identity line `Error-Signature: <app>:<signature>`. Message text is flattened to one line and
backticks become quotes, so an error cannot split the note.

**Merged tickets (T2408).** The board merges similar notes by itself (`DOCS-merge.md`). The combined card carries each member's full text, so the `Error-Signature:` line survives; `ticket.find` matches it there, the `Seen:` line is rewritten in place and no second ticket is made.


- **Dedup** by the `Error-Signature:` line of an open part, and by the ledger (`<run root>/app-errors.json`). A lost
  ledger finds the ticket again by its line; a twin title the todo app refuses is left alone.
- **Count.** The `Seen:` line is rewritten only when the count changed (no note spam).
- **Closed by hand.** A ticket missing from the board for two ticks (a Ship may be closing it right now) is
  forgotten, and the next report makes a new one.

**Start gate**, evaluated for every not-yet-started card on every tick, so a card made at 85 % starts after the
reset (`gate.py`). First that holds is the card's `reason`:

1. `weekly`: `seven_day.utilization` below 0.80, from a probe no older than the probe interval (else read now;
   `oauth.fetch`, saved for the board). No login or no `seven_day` window fails closed.
2. `credits`: the free API credits route takes a turn now (`credits.route.choose`, never `claim`).
3. `free`: the repo is public and the free gateway answers (`freegate.check`). The ticket gets a `Tier: cheap` line
   first, since that line is what lets free models work the card (`DOCS-tiers.md`; it makes the whole repo card
   cheap for that cycle).

A card starts only when it has no run, or its run is `shipped` (the next cycle: a cycle never starts by itself
otherwise). A card at work, shipping, failed or cancelled is left alone. At most one card starts per tick, so a
burst cannot overshoot. A ticket starts at most three times (`starts` in the ledger): a part the session never
ticks must not loop. The start is `Scheduler.start(card, auto_ship=True, extra={app_error: {reason, keys, at}})`.
The per-repo lock (`DOCS-repotask.md`) keeps a second run of the same repo (an umbrella child, an older section
run) waiting. Parts of one repo are one run; a part added while it works rides along or waits for the next cycle.

**Divergence (marker).** The mark is `state.extra.app_error`, not `state.auto_start`: `RunState.closing` is
`auto_start is not None`, so that field would turn the run into a read-only closing run. `contracts/state.schema.json`
documents `app_error`, `phone_update` and `phone_tries`.

## Ship policy: error runs ship and deploy themselves

- They answer to no one like an umbrella child (`umbrella/bounce.py`, `runner/grant.py`: `marks.unattended`): a
  `Q:` or `A:` goes back to work with the reply as the brief, red checks get five fix turns.
- When the checks are green the run ships (`stages._checks`) and deploys per the repo's `deploy:` line
  (`DOCS-landing.md`). Since 2026-11-19 (T2060) every card ships itself, so a part of kuhy's own that the session
  also ticked no longer holds the run for his click (`marks.ships_itself` only matters where a gate is held).
- After the push and the deploy, `appfix.shipped` marks the ledger entries of the ticked parts `shipped` with the
  commit and time.

## After a Ship: resolve, fixed build, reopen (`errors/settle.py`, `loop.py`)

1. `settle` runs the source's `resolve` hook for each `shipped` entry (a failing hook is retried next tick), then
   stores `state: fixed`, `fixed_build` (the `build` hook on the pushed commit; 0 when unknown or the repo is not
   cloned) and `installed_at` (the ship time: the deploy passed before the note closed).
2. A fixed error that reports again **reopens** (a new ticket that names the regression, the gate applies as for any
   error) only when it is a regression:
   - build known on both sides: `build >= fixed_build` reopens, an older build does not;
   - otherwise (kartka today): only an event whose `last_seen` is after `installed_at` reopens. The phone may send
     what it logged before the update; that is not a regression.

## Waiting for the phone (`appfix.py`, `phone_sched.py`)

A deploy that fails because the phone is away is not a failure that needs kuhy. After the failed deploy of a Ship,
`appfix.phone_wait` records `extra.phone_update` when the deploy exited 30 (`phone_deploy.sh`: phone unreachable),
or when the run is an error run and the Pixel (`23181JEGR08034`) is not in `adb devices`. The run rests `failed`
with its error text ("pushed, not deployed ..."), the push stays recorded (`pushed.json`), and
`board.status.compute` says `waiting_phone_update` (column Running, not Needs you). The card line reads "wait for
phone to connect, then update the app"; actions are Retry (deploys now) and Cancel.

`PhoneWatcher` (every 5 s, adb only while something waits) now also lists these cards (`phone_updates`). When the
Pixel attaches it restarts each one (`Scheduler.phone_update_start`): `ship()` sees its own push and only deploys
again (T1968), then closes the note and marks the ledger. Five phone waits per cycle; the sixth failure is an
ordinary one (Needs you). A new cycle forgets `app_error` and `phone_tries`.

The repo card is `failed` meanwhile, so the loop starts no other card of that repo until the update is done.

## The page

The server decides everything (`status`, `column`, `current`, `actions`); the page only draws. A card with tickets
carries `app_error: N` (the number of `Error-Signature:` lines in its text): an icon (`issue`) and the number, names
in `aria-label` and `title`. `waiting_phone_update` has a chip ("Waiting for phone") and the line above. Contracts:
`common.schema.json` `status` and `task_card.app_error`, mirrored in `web/src/lib/schemas-common.ts`.

## Tests

`tests/errors/` (record, adapters, sources, ledger, ticket, gate, marks, loop over the real service backend and a
fake todo MCP), `tests/runner/test_runner_ship_appfix.py` (ship, phone wait, watcher), `tests/board/
test_board_appfix.py`, `web/src/components/app-error.test.ts`; regressions T2009 to T2026
(`tests/regressions/DOCS-errors.md`). Every test runs with a temp HOME, `$TODOIMPL_HOME`,
`$TODOIMPL_ERROR_STATE_ROOT` and `$TODOIMPL_SETTINGS`: kartka's real state file is never read.

## Stalls (`stall/`, T2402, T2403)

Rule (kuhy, 2026-11-20): no running card goes more than 60 s between two real activities. A real activity is one
of the card's own `activity` events in `events.jsonl` (a tool call, text, a result). The board's `system` lines, a
stream heartbeat and a touched file do not count, so nothing looks alive by pinging.

- `stall/watch.py` ticks every 10 s. A card with a live turn (`turn.pid` alive) whose last real activity is over 60 s
  old is one stall episode. A fresh turn counts from its start. An episode counts once however many ticks it lasts.
- Each episode is a line in `<run root>/stalls.jsonl`, its end another line with how long it was quiet.
  `<run root>/stalls.json` holds the open episodes, so a restart never counts one twice.
- Each episode also counts in the board's own contract report, `<error state>/app-errors/todoimplementer.json`
  (kind `perf.stall`). The errors loop turns the record into a ticket like any other app's.
- The signature is the cause (`stall/cause.py`): `stall-memory` (memory pressure on the user slice, checked first,
  because under pressure every other wait is a symptom), `stall-buildlock`, `stall-job-<tool>`, `stall-model`.
- A stall ticket is ungated and first: the loop starts it before any other error card and skips the usage gate for
  it (reason `stall`).

## Defaults chosen (not in the brief)

- One start per tick, three starts per ticket, five phone waits per cycle, 60 s tick.
- A ticket closed by hand comes back on the next report (resolve it at the source to stop it).
- The `free` reason adds `Tier: cheap` to the ticket; `weekly` and `credits` do not.
- A failed deploy with no Pixel attached counts as "waiting for the phone" for error runs only; any run's exit 30
  counts.
- Resolve and `fixed_build` happen once the whole Ship (push, deploy, close) is done, so a fix waiting for the phone
  is not reported fixed yet.
