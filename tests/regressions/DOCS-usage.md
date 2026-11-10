# Usage regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T401 | A resumed session's result total_cost_usd is cumulative; usage summed every result event, double-counting it | tests/usage/test_usage_cost.py |
| T1882 | A stored limit was trusted until its end: the header kept "5 h 76% resets now" and `limit-until` (Fri 10:00) paused every run after both plan limits were reset early; windows past their reset are now dropped, and a read-only plan-usage probe (every 5 min, and on a board request while limited) lifts the limit and the exhausted mark | tests/usage/test_usage_summary.py, tests/runner/test_runner_limitprobe.py, tests/service/test_service_limitprobe.py |
| T1887 | The board poked the limit probe before reading the stored limit, so a fast probe thread could lift it mid-request and `test_t1882` failed about 1 run in 3; the response now reads the limit first and pokes after | tests/service/test_service_limitprobe.py |
