# Usage regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T401 | A resumed session's result total_cost_usd is cumulative; usage summed every result event, double-counting it | tests/usage/test_usage_cost.py |
