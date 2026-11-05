# Deploy regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T502 | run.sh ran xdg-open attached to its stdout, so the browser held the terminal: run.sh never returned and the browser log flooded it | tests/deploy/test_deploy_run.py |
