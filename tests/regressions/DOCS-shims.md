# Test-shim regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T501 | The fake `claude` read a script before renaming it, so two turns on one key raced and the loser crashed with FileNotFoundError | tests/test_shim_claude.py |
| T1927 | The gate run inside a board session inherited `$TODOIMPL_CLAUDE`, so lesson-drafter tests called the real `claude` (not logged in) instead of the shim on PATH | tests/test_hermetic_claude_bin.py |
