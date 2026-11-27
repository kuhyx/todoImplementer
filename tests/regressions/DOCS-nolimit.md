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
