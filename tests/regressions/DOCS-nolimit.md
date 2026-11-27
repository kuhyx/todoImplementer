# No-limit runner regressions

One row per bug or required behaviour, ids global and never reused. The row's test is named `test_t<N>_...`
(pytest) or titled `[T<N>]` (vitest). Feature: `DOCS-nolimit.md`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T2540 | Nothing worked on kuhy's repos while no Claude route ran (kuhy, 2026-11-27). The runner visits only real checkouts under the src root (a `.git` directory, not a linked worktree) whose origin is `kuhyx/*`: a fork or a local-only clone is never pushed or ticketed | tests/nolimit/test_nolimit_repos.py |
| T2541 | The runner must work only while the plan is limited (a `paused_limit` card, the 95 % hold or `limit-until`), the credits take no turn, and the free route has no public waiting card or no gateway | tests/nolimit/test_nolimit_trigger.py |
| T2542 | A step may never run past 60 s: it runs under capped.sh and `timeout`, is cut at the limit and counts as slow (one `slow-nolimit-<step>` ticket per repo and step), never as red | tests/nolimit/test_nolimit_steps.py, tests/nolimit/test_nolimit_run_edges.py |
| T2543 | The runner must never touch kuhy's `~/src/<repo>` working tree: only `git fetch` and `git worktree add` run there; every fix is committed in `<run root>/nolimit/<repo>` on `nolimit/<date>`, and `--no-push` keeps it there | tests/nolimit/test_nolimit_run.py |
| T2544 | A red gate must not leave its fix commit behind or file the same failure twice: the commit is discarded and each failing test is one record of `app-errors/nolimit.json` whose count goes up | tests/nolimit/test_nolimit_run.py |
| T2545 | A green gate pushes the fix fast-forward only (a moved origin is never overwritten) and runs the repo's CLAUDE.md deploy; the repo's earlier failures are marked resolved | tests/nolimit/test_nolimit_run.py |
| T2546 | The runner must stop the moment a Claude route opens: the trigger is asked again before every step | tests/nolimit/test_nolimit_run_edges.py |
| T2547 | One repo per tick, in name order, a new cycle after the last repo; an inactive trigger visits none | tests/nolimit/test_nolimit_tick.py |
| T2548 | `/api/usage` carries the runner's row (`nolimit`: on or off, last repo, last result), valid against `contracts/nolimit.schema.json` | tests/service/test_service_nolimit.py |
| T2549 | The tracking strip shows the row with icons only (wrench, result glyph) and the repo name; its words live in `title` and `aria-label` | web/src/components/nolimit-strip.test.ts |
| T2550 | The first real run filed a false ticket: `eslint --fix .` crashed on a repo whose lint targets `src` (typed rules over files outside the TS project). eslint and prettier now fix only the paths the repo's own `package.json` scripts run them on, and nothing when no script runs them | tests/nolimit/test_nolimit_fixes.py |
| T2584 | After a green gate the repo's `coverage-gaps` files one ticket per uncovered file (at most 10 per visit), counting up on the next visit; an unreadable report is one ticket; the report file never reaches a commit | tests/nolimit/test_nolimit_repo_steps.py |
| T2585 | Prune removes only ended cards' clean worktrees, deletes a branch only when its tip is on origin, never touches a busy card, waiting card or kuhy's checkout | tests/nolimit/test_nolimit_chores_git.py |
| T2586 | Rebase moves a waiting card's clean tree onto origin; a conflict aborts with the tree as it was and files one ticket that counts up; dirty, busy and ended cards are skipped | tests/nolimit/test_nolimit_chores_git.py |
| T2587 | Setup installs every lockfile at the root or one dir down (pnpm, uv, pub), which warms the shared caches | tests/nolimit/test_nolimit_repo_steps.py |
| T2588 | A pin bump is pushed only when the gate stays green; a red one is dropped with a ticket; no freshness gate means no bump; a missing apply script is a ticket | tests/nolimit/test_nolimit_repo_steps.py |
| T2589 | The visibility chore refreshes missing and stale cache entries only, never-cached first; a missing tool is named | tests/nolimit/test_nolimit_chores_rest.py |
| T2590 | The context chore writes the next-turn file once per HEAD with commits, diff and failing tests, the prompt points at it; one chore per tick in rotation; `--chore` runs one now | tests/nolimit/test_nolimit_chores_rest.py |
