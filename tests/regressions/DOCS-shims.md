# Test-shim regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T501 | The fake `claude` read a script before renaming it, so two turns on one key raced and the loser crashed with FileNotFoundError | tests/test_shim_claude.py |
| T2055 | The gate run inside a board session inherited `$TODOIMPL_CLAUDE`, so lesson-drafter tests called the real `claude` (not logged in) instead of the shim on PATH | tests/test_hermetic_claude_bin.py |
| T1983 | ~25 board sessions ran heavy builds (flutter, gradle, pnpm, make, pytest) at once and froze kuhy's PC: two build shims racing must run one after the other, the second saying once who holds the lock | tests/runner/test_runner_buildlock_shims.py |
| T1984 | A build tool started under the held build lock (flutter -> gradle -> java) must run straight away, never wait on the lock its own parent holds | tests/runner/test_runner_buildlock_shims.py |
| T2003 | `make fast` in a board session: the T1920 tests start `make` through the build-lock shim on PATH, which waited on another card's build and timed out at 30 s; the tests mark the lock held so their fake runs start at once | tests/test_makefile_coverage.py |
| T2391 | The flock-shim tests timed out inside a board session: `find_real` skipped only its own shims, so the next `flock` on PATH was the live board's shim, which queued on the real, busy build lock. `find_real` now skips any shims dir that sits beside a `buildlock.sh` | tests/runner/test_runner_buildlock_guard.py |
| T2415 | A one-second gate step (`make lines lint`) waited 179 s in the build queue behind other cards' godot and flutter builds, so the card was filed as stalled: `make` was a locking shim and `uv run ruff` locked too. `make` is no shim (a stale one is deleted) and `uv run <linter>` skips the lock | tests/runner/test_runner_buildlock_light.py |
| T2416 | `make test` in a board session ran past the 60 s action cap in one call: `make test-shard SHARD=k` (k = 1..SHARDS) runs shard k of the suite, files dealt by size, filtered at collection so each dir keeps its own `conftest`; `make test-cov` combines and enforces 100 % | tests/test_test_shard.py |
| T2417 | A test shard waited 53 s for the build lock inside capped.sh's 60 s scope and was killed after 5 s of work: `TESTCAP` and `WEBCAP` put the lock-taking `uv run` or `pnpm` first, so the wait happens outside the scope | tests/test_makefile_lockfirst.py |
| T2419 | Heavy builds queued 4-6 deep behind multi-minute godot runs on the one build slot; kuhy picked three at once (2026-11-21): `SLOTS` slot locks, each with its holder, and a waiter goes once fewer than three live tickets are ahead | tests/runner/test_runner_buildslots.py |
| T2420 | With more than one slot a waiter blocked on the ticket right before it would start only when that one build ended, not when any did: it now blocks 2 s at a time and counts again | tests/runner/test_runner_buildslots.py |
| T2421 | A waiter on slot 1 or 2 was invisible to `bgwait.waiters` (the dead-wait judge would kill it), a board check could not take a free slot, the stall detail named only slot 0's holder and a hand-held flock on a slot holder slipped past the guard | tests/runner/test_runner_buildslots.py |
| T2422 | The hold ceiling watched only the first ticket in the queue: a quiet holder in another slot kept its slot for ever. It now watches every held ticket | tests/runner/test_runner_buildslots.py |
| T2423 | `make test-cov` ran `capped.sh uv run coverage combine`: uv queued on the build lock inside the 60 s scope and was killed. `coverage` joins the light tools (it only reads data files) and the Makefile calls `uv run coverage` directly | tests/runner/test_runner_buildlock_light.py |
| T2424 | Builds that held the one slot for minutes (godot --import, flutter test, pre-commit --all-files) were waited out, never fixed: the hold ceiling now files each build that holds a slot over 60 s as a `perf.heavybuild` ticket in its own repo | tests/runner/test_runner_heavybuild.py |
