# Server and gate regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...` (pytest) or titled
`[T<N>] ...` (vitest); `scripts/check_regressions.py` fails on a row without a test or a tag without a row.

| Id | What went wrong | Test |
| --- | --- | --- |
| T101 | `service._act` let the runner's RunnerError(message, code) escape, so every refusal (not_found, conflict, disabled, bad_request) became HTTP 500 | tests/service/test_service_errors.py |
| T102 | Scheduler stage/done events carried only `{type, stage}` / `{type}`, so SSE payloads failed contracts/live.schema.json (no status, column, current, needs, actions) | tests/service/test_service_live.py |
| T103 | Once every section of a note was shipped the note closed, `list_tasks` stopped returning it and its shipped cards vanished from /api/board (Done column always empty) | tests/service/test_service_closed.py |
