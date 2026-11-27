# The no-limit runner: work the board does with no Claude usage at all

kuhy (2026-11-27): when no Claude route can run a turn (the plan is limited for 12 h to 4 days, the free API
credits are not `ready`, the free gateway is down or no public card waits), the board should still do useful
work that costs no tokens. Code: `server/todoimpl/nolimit/`. Regressions: `tests/regressions/DOCS-nolimit.md`
(T2540 to T2550, T2584 to T2590, T2600, T2601).

## What the board can do with no tokens, ranked

Ranked by what it saves the next Claude turn, then by risk. "Built" means this runner does it today.

| # | Work | Built |
| --- | --- | --- |
| 1 | Rerun each repo's full gate (`gate`, else `test` from its CLAUDE.md) and file one ticket per failure through the errors loop, so a red repo is known before a card lands on it | yes |
| 2 | Apply the repo's own lint and format autofixes (ruff, eslint, prettier), commit them, push fast-forward and deploy when the full gate is green | yes |
| 3 | Cut any step at 60 s and file one slow-step ticket per repo and step, so a slow gate is fixed before a card waits on it | yes |
| 4 | Install each repo's locked deps in a fresh worktree; a lockfile that is not frozen (the install changes the tree) is a ticket | yes |
| 5 | Precompute each waiting card's next-turn context (diff against its base, gate output, failing tests) into `<run>/nolimit-context.md`, and make the next prompt point at it | yes |
| 6 | Bump dependency pins to the newest stable versions (the freshness gate's list), run the full gate, push on green | yes |
| 7 | Rebase stale board worktrees of waiting cards onto origin, so the next turn starts from a current base | yes |
| 8 | Run each repo's `coverage-gaps` and file the uncovered lines as tickets | yes |
| 9 | Warm the shared caches (pnpm store, uv cache, Flutter pub cache) so the next turn's installs run offline | yes |
| 10 | Prune board worktrees and branches of shipped or cancelled runs, and report the disk it frees | yes |
| 11 | Refresh the repo visibility cache (`free-llm-check-dir`) for every repo, so the free route knows which cards are public | yes |

## When it runs (`trigger.py`)

All three must hold. The runner asks again before every step, so it stops the moment any route opens
(result `stopped`).

1. The plan is limited: a card rests `paused_limit`, the 95 % weekly hold is on (`usage-hold.json`), or
   `limit-until` has not passed.
2. The free API credits take no turn: `credits.route.choose` picks no `credits` (not `ready`, or over the
   weekly cap).
3. The free route is unusable: no card waiting on the limit may go free (a public repo, no `Error-Signature:`
   line), or the gateway is down (`runner.freeok`'s cached probe).

## Which repos (`repos.py`)

Every directory under the src root (`$TODOIMPL_SRC`, else `~/src`) with a `.git` directory (a linked worktree is
skipped) and an `origin` owned by `kuhyx` (read from `.git/config` as written). The runner never pushes to, or
files a ticket for, a repo kuhy does not own. Commands are the backticked bullets of its CLAUDE.md. The full gate
is `gate`, else `test`. A repo with neither is read-only: its `lint` runs, nothing is committed.

One repo per tick, in name order. A cycle visits each repo once; after the last one a new cycle starts.
A repo whose step was cut is done for the cycle like any other and is tried again in the next one.

## One visit (`run.py`)

1. `git fetch` in kuhy's checkout, then the board worktree `<run root>/nolimit/<repo>` on `nolimit/<date>`
   from `origin/<default>` (`git worktree add`, or a forced checkout of an existing one). These two are the only
   commands that touch `~/src/<repo>`, and both write inside `.git` alone. Branches of other days are deleted.
2. Setup: `pnpm install --frozen-lockfile --prefer-offline`, `uv sync --frozen` and `flutter pub get
   --enforce-lockfile` for every lockfile at the root or one dir down (`app/`, `web/`). This also warms the
   shared stores (pnpm store, uv cache, pub cache), so the next turn installs offline (#9, T2587).
3. Autofixes, picked from the repo's config: ruff when it is configured; eslint and prettier only on the
   paths the repo's own `package.json` scripts run them on (T2550), never on the whole tree. A fixer that finds errors it cannot fix exits 0 (the gate reports
   them); only a crash is red, and its changes are dropped.
4. A commit of what changed (`git add -A`, the repo's own commit hooks run, never skipped).
5. The full gate. Red: the commit is discarded and each failure is a ticket. Green: the repo's earlier no-limit
   records are marked resolved; then, unless `--no-push` or nothing was committed, `git push origin
   HEAD:<default>` after checking that origin is an ancestor (fast-forward only), and the CLAUDE.md `deploy`.
6. Still green, before the push: `coverage.py` runs the repo's `coverage` bullet (unless `n/a`, T2601), then its `coverage-gaps` bullet with `--json --max-files
   10` and files one ticket per uncovered file (`nolimit-coverage-<sha8 of path>`; an unreadable report is
   `nolimit-coverage-gaps`, #8, T2584). Then `bump.py`, only in a repo with
   `scripts/check_dependency_freshness.sh`: `~/.claude/scripts/apply_dep_pins.py .`, relock (`uv lock`,
   `pnpm install --lockfile-only`, `flutter pub get`), one commit, the gate again. Green: the commit is pushed
   with the rest. Red: the commit is dropped and each failure is a `nolimit-bump*` ticket (#6, T2588).

Every repo command runs as `capped.sh timeout -k 5 60 bash -c <command>` (`steps.py`, through
`runner.checks.run_capped`, so a build waits for the build lock first). Git plumbing (fetch, worktree, status,
reset) runs through `runner.worktree.git` with the same 60 s limit.

## Chores (`chores.py`)

After the tick's repo visit, one board-wide chore runs, in turn: `prune`, `rebase`, `context`, `visibility`.
Each stops after 45 s (the rest waits for its next turn), asks `still()` before each card, and runs every
command as a capped step under 60 s. Cards are the run dirs whose `state.json` names a worktree (`cards.py`):
ended (shipped, closed, done manually, cancelled), busy (`turn.pid` exists: never touched) or waiting.

- `prune` (#10, T2585): an ended card's clean worktree is removed (`git worktree remove --force` from the
  owning repo, after `du -sb`); its branch is deleted only when its tip is on origin. A tree with changes stays.
  The report names each card and `freed_bytes`.
- `rebase` (#7, T2586): a waiting card's clean tree is rebased onto `origin/<base>`; a conflict aborts (the
  tree is as it was) and files `nolimit-rebase` for the card's repo.
- `context` (#5, T2590): `<run>/nolimit-context.md` per waiting card: commits on top of `origin/<base>`, the
  diff stat, uncommitted files, the repo's `test-changed` output and the failing tests it names, stamped with
  HEAD (an unchanged HEAD is skipped). `prompts/nolimitctx.py` adds "read <file> first" to the next prompt.
- `visibility` (#11, T2589): `free-llm-check-dir <repo>` for each `~/src` repo whose cache entry is missing or
  older than 20 h, never-cached first; the tool missing is an `error` in the report.

Reports land in `nolimit.json` under `chores` (`at`, `report`) and `chore_next`. CLI: `--chore <name>` runs one
now, whatever the trigger.

## Tickets (`tickets.py`)

- **Red step**: one record per failing test the output names (pytest `FAILED <id>`, vitest `FAIL <file>`),
  else one for the step. File: `<error state>/app-errors/nolimit.json`, kind `nolimit.red`, signature
  `nolimit-<step>[-<sha8 of the test id>]`, app the repo's directory name. The same failure seen again counts
  up; the errors loop makes one ticket per `<app>:<signature>` (`DOCS-errors.md`).
- **Cut step**: `stall.slowstep.file`, signature `slow-nolimit-<step>`, the same ticket a stalled card's gate
  step files (starts first, ungated).

## Results and the tracking strip (`status.py`)

`<run root>/nolimit.json` keeps the cycle, whether the trigger held at the last tick, and the last visit.
`GET /api/usage` carries `nolimit` (`contracts/nolimit.schema.json`): `active`, `repo`, `result`, `at`.

| Result | Meaning | Glyph |
| --- | --- | --- |
| `deployed` | green, fixes pushed, deploy ran | install |
| `pushed` | green, fixes pushed, nothing to deploy | up arrow |
| `green` | green, nothing pushed (no fix, or `--no-push`) | check |
| `red` | a step failed; its tickets are filed | warning triangle |
| `slow` | a step was cut at 60 s; its ticket is filed | hourglass |
| `stopped` | a Claude route opened mid-visit | cross |
| `readonly` | no gate: lint only | eye |

The strip (`web/src/components/nolimit-strip.ts`) shows a wrench, the repo name and the result glyph, dimmed
while the runner rests; a resting runner with no visit yet shows nothing. Words live only in `title` and `aria-label`.

## Running it

- Server: `service.build_backend` starts `nolimit.tick.Loop`, one tick every 5 min on its own thread.
- CLI: `PYTHONPATH=server .venv/bin/python -m todoimpl.nolimit.tick --repo <name> --once [--no-push]`.
  `--repo` visits that checkout now, whatever the trigger says. Without `--repo`, `--once` runs one tick as
  the server would; with neither flag it loops like the server.
