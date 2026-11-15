# Test-shim regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T501 | The fake `claude` read a script before renaming it, so two turns on one key raced and the loser crashed with FileNotFoundError | tests/test_shim_claude.py |
| T1927 | The gate run inside a board session inherited `$TODOIMPL_CLAUDE`, so lesson-drafter tests called the real `claude` (not logged in) instead of the shim on PATH | tests/test_hermetic_claude_bin.py |
| T1983 | ~25 board sessions ran heavy builds (flutter, gradle, pnpm, make, pytest) at once and froze kuhy's PC: two build shims racing must run one after the other, the second saying once who holds the lock | tests/runner/test_runner_buildlock_shims.py |
| T1984 | A build tool started under the held build lock (flutter -> gradle -> java) must run straight away, never wait on the lock its own parent holds | tests/runner/test_runner_buildlock_shims.py |
| T2003 | `make fast` in a board session: the T1920 tests start `make` through the build-lock shim on PATH, which waited on another card's build and timed out at 30 s; the tests mark the lock held so their fake runs start at once | tests/test_makefile_coverage.py |
