# Sessions land their own work (kuhy, 2026-11-09)

Board sessions kept parking cards on asks that were only permission ("OK me to commit and push", "press Retry",
"send a `LONG:` turn", "editing main is off-limits"). The decision: a session lands its own work and asks kuhy only
for what he alone can give.

## The grant (`server/todoimpl/prompts/standing.py`, T2053)

Every work-stage prompt (implement, fix, resume, fresh, live_check) carries it:

- Commit freely in the worktree. To land: `git fetch`, rebase onto `origin/<base>`, run the repo's gate,
  `git push origin HEAD:<base>`, push any tags. `<base>` is the repo's default branch (`extra["base_branch"]`).
- Never edit or commit in kuhy's own checkout (`~/src/<repo>`) working tree. Work in another repo goes in a worktree
  the session creates under its run dir (`git -C ~/src/<other> worktree add <run dir>/wt-<name> -b todo/<item id>
  origin/main`), landed the same way. `~/src/todo` is edited the same way.
- Free workers (T2464) get the same limit by force: their task file names the child's repo ("everywhere" means that repo
  only), their prompt names the worktree, and `Edit`/`Write`/`MultiEdit`/`NotebookEdit` are denied under `~/src`
  (`$TODOIMPL_SRC`). An umbrella note saying "every app" had sent workers into nine other repos' checkouts.
- Also granted: installers, confirm scripts and other repo scripts, marker files, approving its own drafts.
- Heavy commands still go through `capped.sh`. Every tool call is one step that ends within 60 s (one gate step or
  test shard, push and deploy as calls of their own), because the stall watch files any quiet stretch over 60 s
  as a top-priority bug (T2411). Only a job that cannot be split (a release build) runs via
  `systemd-run --user --collect` while the session waits.
- kuhy is asked only for a `Q:` question round, a decision, a check only he can hear (audio) and physical taps.
  Phone, device, emulator and E2E checks are the session's own (T2048).

Sessions need the session policy (`~/.config/todoImplementer/session-policy.json`) to push: without one the built-in
`git push` deny still applies (DOCS-spec.md, "Permission blocks heal themselves").

## Backstop (`runner/grant.py`, T1863)

A turn that ends on `A:` whose concrete ask (`board/ask.py`) is permission (OK me, approve, permission, may I, whether
to commit|push|merge, press Retry, send a `LONG:`, write ... by hand, run ... yourself, after the server commits,
off-limits ...) or any ask for something Claude can run itself (a command, a deploy such as `deploy-todoimpl`, a restart,
sudo, a push, a write under ~ outside ~/src/<repo>; T2006) resumes the same session with a fixed `(runner) Granted: do it yourself ... run it,
then rerun the card's checks` note and a feed line `auto-granted, the session resumes: <ask>`. Never granted: asks only
kuhy can answer (phone, Pixel, plug, tap, screen, screenshot, audio, a password, login, token or secret, a decision such
as "which ..." or "do you want ...") and a reply with an `ask` block holding a `choice` or `screenshot`. Bounds: once per
stage (`extra["ask_grants"]`, cleared when a turn ends on anything but `A:`) and twice per run (`extra["ask_grant_total"]`,
cleared by Start, Retry and a note from kuhy). The count is saved before the granted turn starts, so a restart cannot
grant the same ask twice. A further ask parks the card as before. Not used in the spec and plan stages, nor while a
phone wait is set. No LLM. The standing grant tells sessions the same: never end on `A:` for what you can run.

### Self-resume (`runner/resume.py`, T2104)

An `A:` whose resume text is only commands and waits (`Resume by ...`, `is-active`, `when it finishes`) with nothing of kuhy's in it (no plug, audio, Ship click, credential, decision, ask block; a phone/screen check is Claude's own) does not park: the run rests in `paused_retry` on the retry ladder (1, 2, 5, 10 min, then 30 min) and the stage reruns with the ask as `(runner) Resume it yourself` prompt. 12 passes per run (`extra["self_resumes"]`, cleared by Start, Retry and a note), then the card parks as before. A phone wait the Pixel was already in (`tried_attached`) stays set and is no cable ask; an untried one is kuhy's cable and is left alone. Runs before the grant backstop and, unlike it, does not skip a phone wait.

## Where a repo lives (kuhy, 2026-11-19; `board/repos.py`, `board/clone.py`, T2079)

The board used to assume `~/src/<name>`; claude-config lives in `~/.claude`, so its Start said "repo not found".
`repo_path` is the one resolver (board check, runner `repo_dir`, ship, deploy, closing, triage), in this order:

1. The override file `~/.config/todoImplementer/repo-paths.json` (`$TODOIMPL_REPO_PATHS`): `{"owner/name": "/abs/path"}`.
2. `~/src/<name>` (`$TODOIMPL_SRC`), unless its origin is some other repo.
3. A map from origin remote (`github.com/<owner>/<name>`, https or ssh, case-blind) to checkout, built by one-level
   scans of `~/src/*`, `~/src/testsAndMisc/*`, `~/praca_magisterska` and its children, and `~/.claude`
   (`$TODOIMPL_REPO_ROOTS`, an `os.pathsep` list, replaces all but `~/src`). Kept 10 min; rebuilt on any miss and when
   a hit's checkout is gone. Never a recursive walk of `~`.
4. Nothing found: `~/src/<name>`, the path Start clones into.

A relative repo is never "missing" on the board. The first attach of a run (`repo_dir(clone=True)`) with no checkout
runs `gh repo clone owner/name ~/src/<name>` (15 min cap), as the new-repo flow does; a failed clone ends the run in
Needs you (`run_failed`, Retry works) with gh's error. Absolute-path repos still show "repo <path> not found".
A new project (T2377): when gh says the repo does not exist ("Could not resolve to a Repository") and its owner is
`kuhyx`, Start runs `gh repo create kuhyx/<name> --private|--public --add-readme` (a README commit on the default
branch, so worktrees branch off it), clones it, and the run goes on; the session writes the scaffold. A note line
`visibility: public` (or `private`, outside code fences, case-blind) picks the visibility; no line, or both, means
private. Any other clone failure (network, auth) and any other owner fail as before and create nothing. The
standing grant tells sessions to write that line on every new-project note they file.
Sessions work in their own worktree off the resolved checkout; Ship, closing and deploy run there too, so claude-config
deploys with a pull in `~/.claude` (`- deploy:` line of its CLAUDE.md: a ff-only pull there).

One name per real repo (T2272): `repos.canonical` names a repo by the hosted origin of the checkout it runs in
(the URL's own case). feedback_inbox filed `kuhyx/cleanup-plate`, a repo that does not exist, for ~/src/cleanup-plate,
whose origin is `Sepci0/cleanup-plate`; the board listed both and gave each a card. Now the board fetch rewrites an
open note filed under another spelling (owner, name or case) through `update_task` (so `list_tasks(repo=)` finds it), shows closed notes
and shipped runs under the origin (one Done card per repo: the real name's own run dir, else the newest), and the
New task form files a typed alias under the origin. A repo with no checkout, or a checkout with no hosted origin
(a local bare path, no remote), keeps its name. Answers are kept 10 min.

## Rebase on every drive (`runner/worktree.py`, T1864)

`attach` runs at the start of each drive: fetch, then `git rebase --autostash origin/<base>` in a reused worktree,
and `base_sha` is recomputed. Work the session already pushed (HEAD on origin, past the old base) is left alone and
keeps its old base, so the drawer diff still shows it. A conflict is left as git left it (never aborted):
`extra["rebase_conflict"]` makes every prompt carry "the worktree was rebased onto <ref> and has conflicts: resolve
them first" until HEAD contains the ref again. No rebase in the Ship drive or while an adopted turn is still editing
(T1866); Ship refuses a tree with unresolved conflicts instead of committing the markers.

## Ship by itself (kuhy, 2026-11-19; `runner/hold.py`, T2060)

kuhy: "Ready to ship category and column is stupid if it is ready to ship just ship automatically". A card whose
plan, live check and checks are green goes from `checks` straight to `shipping` (squash, rebase, gate, push ff-only,
deploy per the repo's `deploy:` line, close), and a closing run closes its note as soon as its own re-run is green.
No click, no `Ready to ship` / `Ready to close` status or column; `shipping` shows in Running.

- **Loader.** The card's line reads `shipping: <step>` (squashing the work, rebasing, running the checks, pushing,
  deploying, closing the note) from `run.extra.ship_step`, set by `ShipPlan.step`; the web card draws a spinner
  before it. Each step also lands in the activity feed.
- **Restart.** A run found at `gate` when the server starts (an older server left it) is queued in `shipping`, a
  closing one in `closing` with `close_only` (no second Sonnet turn): `runner/recovery.py`.
- **Failure.** Any Ship or deploy failure takes the paths below and in `DOCS-errors.md` (Needs you with Retry,
  the session fix turns, "pushed, not deployed"). Retry of a failed Ship goes to `shipping`, never to a rest.
- **No buttons.** The board offers no Ship, Close or Auto-ship tick; the `ship` and `close` routes and relay kinds
  stay and answer `disabled`. A stuck card is a failed one: Retry.
- **FCM.** The "ready" ping is gone (`DOCS-native-app-relay.md`).
- **Test seam.** `TODOIMPL_HOLD_GATE=1` brings the old rest at `gate` back. Only the test suite sets it
  (`tests/conftest.py`), to drive Ship by hand; `tests/runner/test_runner_ship_all.py` runs the real rule.

## Ship (`runner/ship.py`, T1865)

A branch the session committed ships as before (squash, rebase, gate, push). A branch with a clean tree whose HEAD is
on origin gets no new commit and no push: it closes with "Pushed by the session: <short shas>." and cleans up, and
`state.ship` has no `pushed_at`. Its checks run again first (T1964), because the session never ran them for this
HEAD: red checks end in Needs you and nothing is deployed. Partly pushed work squashes only what origin lacks (the
merge base is the last pushed commit). Every path that pushed then deploys (below) before it closes the note.
A round that changed no code (clean tree, HEAD on origin, nothing past `base_sha`) closes the same way with
"Closed with no code change." after its checks, Ship click or auto-ship (T2361); only local commits whose net diff is
empty and that origin lacks still end in "Nothing to ship".

## Done means deployed (kuhy, 2026-11-11; `runner/deploy.py`, `runner/deployhost.py`, T1960-T1962, T1964-T1970)

A change is not done until it is installed, released and deployed everywhere it runs. After a successful push (and on
the "session already pushed" path) and before the note closes, Ship runs the repo's deploy. A close with no code change
(nothing pushed) deploys nothing.

- **Declaration.** The repo's CLAUDE.md, Commands section, has a bullet ``- deploy: `<command>` `` (same shape as
  `- run: ...`). Ship reads it from the worktree at the pushed HEAD (`git show HEAD:CLAUDE.md`, first match outside
  code fences), never from `~/src/<repo>`. The command runs in the worktree through `capped.sh` (4 GiB, 20 % CPU) and
  must be idempotent and exit non-zero unless its own health check passes. A repo where nothing runs or installs
  anywhere says so with ``- deploy: none (<why>)`` (T2342, `runner/deployline.py`): a reason is required, no unit
  starts, and the evidence reads ``deploy `none (<why>)` exit 0: nothing to deploy``.
- **Where it runs.** Like the pre-push gate (`DOCS-spec.md`), as its own transient unit `todoimpl-deploy-<card>`
  (`systemd-run --user --collect`, `RuntimeMaxSec` 4 h), one at a time with gates (the `gate.lock` flock). The host
  kills the command after 1800 s and writes `<run dir>/deploy/exit.json` (`commit`, `ok`, `exit`, `command`, `tail`,
  `log`); the server only waits for that file. A green record for the same commit is reused, a unit still running is
  waited for, a red or missing one starts again. Tests swap `deploy._run`; with `TODOIMPL_TURN_LAUNCH=direct` the host
  is a detached child.
- **Outcomes**, all `NeedsYouError` kind `run_failed` (no schema change), the note open and the worktree kept:
  `pushed, not deployed: <repo> declares no deploy: command in CLAUDE.md`;
  `pushed, not deployed: deploy failed (exit N): <tail>` (also `timed out`); a success adds
  ``deploy `<command>` exit 0:`` and its tail to the close evidence.
- **Retry never pushes twice.** After the push Ship writes `<run dir>/pushed.json` (commit, time, the green check
  results). Retry on a "pushed, not deployed" failure goes straight back to Ship (no gate click); Ship sees the record
  matches HEAD and origin has it, skips squash, push and checks, and deploys again. The evidence then says "Shipped
  <sha>" as for a first-time push. Any drive but Ship (a note from kuhy sends the run back to implement) drops the
  record first, so new work is squashed and pushed as usual (T1970); after every deploy the worktree is reset to HEAD
  and cleaned (`git reset --hard`, `git clean -fd`), so build leftovers never reach a later squash.
- **A restart mid-Ship** (todoImplementer's own deploy restarts the server; T1988): recovery queues every run found in
  `shipping` again, no click and no Needs you. Ship is idempotent at each cut point: before the push it squashes and
  pushes; after the push, before `pushed.json`, it recognises the push on origin (`_landed`) and goes on to the checks
  and the deploy; mid-deploy it adopts the running unit or its record; after the deploy it reuses the green record and
  closes (closing a closed note overwrites the evidence); a rebase the restart cut half way (`<run dir>/rebasing`) is
  aborted first. At most 2 automatic resumes per click (`ship_resumes`, reset by Ship and Retry); then the run fails
  "Ship was interrupted by a restart N times in a row ..." and Retry goes straight back to `shipping`, as does Retry on
  the older form of that failure. An umbrella child is resumed the same way, and a child found in `shipping` takes
  its repo's lock with `force` (it was already working): it never queues behind another run of the repo, so a restart
  cannot burn a resume while the Ship waits (T2463).
- **Deploy into kuhy's checkout (T2007).** A deploy that starts with `git -C ~/src/<repo> pull --ff-only` fails when
  that checkout has uncommitted edits at paths the push changed (git: "would be overwritten by merge", tracked or
  untracked). `runner/deployheal.py` reads that text from the failed record only. If every blocking file already equals
  the incoming content (a session wrote the same change there) and the index holds nothing of kuhy's (a staged edit of
  his counts as his), it restores them (tracked: back to HEAD; untracked: removed) and deploys again at once. A git
  failure while healing (his own git holds a lock) waits the same way. Otherwise it touches nothing: the run rests in `paused_retry` ("deploy
  waits: edits in ~/src/<repo> block the pull (<file>)") on the backoff ladder, 12 waits (`shipfix.MAX_DEPLOY_WAITS`,
  counter `retries`), and the resumed Ship only redeploys (`pushed.json`). After the 12th it ends in Needs you naming the
  files: "commit or discard them, then Retry". "waiting for build lock held by ..." in such a tail is the first log line
  of any queued check (`buildlock.held`, outside the timeout), not a cause.
- **Checks red after the rebase (T2008).** Ship's re-run of the checks on the rebased tree used to end in Needs you.
  Now the session gets a fix turn (red tails, "fix them yourself: commit, rebase, push, deploy"), same bounce and counter
  (`ship_fixes`, 2) as a refused commit; the third time is Needs you. `ask_grants` could not bound it: a finished turn
  clears it.
- **Deploy red after the push (T2050).** `DeployFailedError` (exit N or timeout) no longer waits for a Retry click: the
  session gets a fix turn with the deploy output and "fix it yourself: bump and tag the changed package, push,
  redeploy, read the result" (a deploy check like "X changed after <tag>: bump and release" is its job, `DEPLOY` in
  `prompts/standing.py`). The implement drive drops `pushed.json`, so its commits and tag ship as pushed work and the
  deploy runs again. 2 fix turns per Start (`deploy_fixes`, `shipfix.MAX_DEPLOY_FIXES`; Start, Retry and a note clear
  it), then Needs you; its text leads with the deploy's own `FAIL` lines when the 600-char tail would cut them. A
  phone wait (`appfix.phone_wait`) comes first; a blocked pull (T2007) gets no fix turn. Umbrella children get it
  too (T2343). A failure that is not the phone's (exit 30) drops the phone wait an earlier deploy left (T2465).
- **Umbrella card.** Children that are pushed but not deployed are listed apart from children that need kuhy:
  `3 of 7 children need you: a (why); b. 4 pushed, not deployed: c (declares no deploy: command in CLAUDE.md); ...`.
- **Self-healing.** The implement prompt (`prompts/standing.py`, `DEPLOY`) tells a session to add the line when the repo
  lacks one, and a Ship that finds none sends the session back to add it (below).

## Ship failures Claude can fix (kuhy, 2026-11-19; `runner/shipfix.py`, `umbrella/revive.py`, T2340-T2344)

Umbrella 2556952d-0 sat in Needs you with 24 children whose failures were all Claude's work. Only a physical tap,
a secret only kuhy has or a decision with no recommended answer may stay in Needs you. `shipfix.heal` routes the
rest. A plain rerun rests the run in `paused_retry` (kind `killed`) on the retry ladder and resumes at `shipping`.
A fix turn goes to `implement` with a brief and `reship`, and the push record is dropped first, so edits the
session leaves are squashed and pushed. Start and Retry clear every counter (also a child's, `umbrella/run.py`).

| Failure (`NeedsYouError` subclass) | First | Then | Bound, then Needs you |
| --- | --- | --- | --- |
| Gate step killed while its log holds only the build lock's wait line (`GateRedError.waited_only`) | rerun, not counted as a kill | rerun | `gate_waits` 12 |
| Gate step killed by a signal (exit < 0, 137, 143), e.g. OOM at capped.sh's 4 GiB | one rerun (`gate_kills`) | fix turn: shard it finer or cut its memory | `ship_fixes` 2 |
| Gate step red (`GateRedError`) | fix turn with its tail | fix turn | `ship_fixes` 2 |
| No `- deploy:` line (`NoDeployLineError`) | fix turn: add a working line and run it, or `- deploy: none (<why>)` | fix turn | `deploy_fixes` 2; the text then says Retry gives 2 more |
| Deploy busy: exit 52, "rerun later" (tunedeck while it plays music, T2409) | rerun on the ladder, no fix turn | rerun | `retries` 12 (about 4 h) |
| Deploy red (`DeployFailedError`), umbrella child or not | phone wait if the phone is why; a kill (exit < 0) reruns once (`deploy_kills`) | fix turn with the deploy log tail | `deploy_fixes` 2 |

The -15 exits of 2556952d's gate steps (habit_stack, screen-locker, home_inventory) were OOM kills of the step's
capped scope after it had the build lock, not a timeout of the wait: the queue is outside every step's timer
(`buildlock.held`), and the wait line is only the first log line.

**Children that already failed (T2344).** `recovery.interrupted` (server start) looks into every failed umbrella:
`revive.children` rebuilds each failed child's failure from its error text (a deploy's tail from
`<child>/deploy/exit.json`) and asks `shipfix.heal`. A rerun puts the child in `shipping` at once (its
`ship_resumes` start afresh), a fix turn in `implement`; the count is saved before any drive, so restarts never
revive a child without end. When any child revived, the umbrella goes back to `implement` and is queued.

## A resting run frees its disk (`runner/reap.py`, T2433)

Ship removed only `<run>/wt`; the `<run>/wt-<name>` worktrees sessions add for other repos and their venvs stayed
(the run root reached 112 GB). When a run comes to rest at `shipped`, `closed`, `cancelled` or `done_manually`
(drive end, Close, an idle Cancel or Done manually), a thread removes every clean `<run>/wt*` worktree through the
repo that owns it (`git worktree remove --force`, `prune`), deletes its `todo/*` branch when every commit is on a
remote or landed by content (`git cherry`), keeps it otherwise (Retry and Restart re-add the worktree from it), and
deletes top-level venvs and `node_modules`. It never touches a worktree with uncommitted changes, a run with a live
turn, a pending inbox, handoff or Done-manually file, a dir some process has as cwd, or a run a Start took back
(asked again before each worktree). First it stops every active user service whose WorkingDirectory is in a
`<run>/wt*` dir (`runner/units.py`, T2494: a session's dev server outlived its worktree). state.json, events, logs,
shots and turn files stay: the board reads them.
Older runs: `python -m todoimpl.runner.sweep [--apply] [--exclude <run id>] [--budget 20]` (dry run by default,
failed runs included; the budget is checked before each worktree, exit 3 = spent, run it again). A Done
manually click that a restart settled (`stopping.recover`) waits for the next sweep.
