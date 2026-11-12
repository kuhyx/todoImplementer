# Usage regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T401 | A resumed session's result total_cost_usd is cumulative; usage summed every result event, double-counting it | tests/usage/test_usage_cost.py |
| T1882 | A stored limit was trusted until its end: the header kept "5 h 76% resets now" and `limit-until` (Fri 10:00) paused every run after both plan limits were reset early; windows past their reset are now dropped, and a read-only plan-usage probe (every 5 min, and on a board request while limited) lifts the limit and the exhausted mark | tests/usage/test_usage_summary.py, tests/runner/test_runner_limitprobe.py, tests/service/test_service_limitprobe.py |
| T1887 | The board poked the limit probe before reading the stored limit, so a fast probe thread could lift it mid-request and `test_t1882` failed about 1 run in 3; the response now reads the limit first and pokes after | tests/service/test_service_limitprobe.py |
| T1910 | GET /api/usage re-read every stream of every run on each request (340k events, 10 to 17 s under load); a stream whose mtime and size are unchanged is now folded once for costs and once for rate limits | tests/usage/test_usage_memo.py |
| T1997 | `python -m todoimpl.tokens.audit --recommend` was killed at the 60 s cap: it re-read every transcript on each run (11 days, 7.3 GB, 58.7 s; the notes section alone scanned the whole root and re-priced every linked session for 26 s) and parsed each in-window file twice; per-file results (note facts, window sessions, lifetime spend) are now cached by path, size and mtime, and a rerun re-parses only changed files with an identical report | tests/tokens_audit/test_audit_cache.py |
| T1927 | The usage page's Model dropdown and per-model tables listed every raw id (nemotron `:free`, three Haiku, two Opus, two Sonnet versions); they now show Free (any non-`claude-*` or `:free` id), Haiku, Opus and Sonnet, an unmatched Claude id keeps its row, and the model filter takes a group | tests/tokens_api/test_tapi_model_groups.py |
| T1996 | /api/usage titled 57 of 149 run dirs with their bare id ($901, 39 % of spend): only cards on the board were looked up, not the parts of a repo card or the todo note of a closed or regrouped run; a section headed just "What" was shown as that label | tests/service/test_service_usage_titles.py |
