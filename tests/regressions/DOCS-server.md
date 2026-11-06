# Server and gate regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...` (pytest) or titled
`[T<N>] ...` (vitest); `scripts/check_regressions.py` fails on a row without a test or a tag without a row.

| Id | What went wrong | Test |
| --- | --- | --- |
| T101 | `service._act` let the runner's RunnerError(message, code) escape, so every refusal (not_found, conflict, disabled, bad_request) became HTTP 500 | tests/service/test_service_errors.py |
| T102 | Scheduler stage/done events carried only `{type, stage}` / `{type}`, so SSE payloads failed contracts/live.schema.json (no status, column, current, needs, actions) | tests/service/test_service_live.py |
| T103 | Once every section of a note was shipped the note closed, `list_tasks` stopped returning it and its shipped cards vanished from /api/board (Done column always empty) | tests/service/test_service_closed.py |
| T104 | The /api/live connect snapshot of a card never run sent `stage: null`, which live.schema.json and its Zod mirror rejected, so opening any backlog card toasted "live stage: stage: Invalid option" | tests/http/test_http_live.py, web/src/lib/live-feed.test.ts |
| T901 | After a restart every recovered run landed in Needs you with "unknown task <card>": build_backend started the Scheduler (whose recovery drives call get_task) before the first note fetch filled the cache | tests/service/test_service_build.py |
| T1402 | Task repo "kuhyx/todo-app" showed Start disabled "repo ~/src/todo-app not found": repo_path ignored checkouts whose directory name differs from the repo name (~/src/todo) | tests/board/test_board_repo_path.py |
| T1100 | A claude_action/claude_question card showed the generic "see the feed" text instead of the session's last `A:`/`Q:` line | tests/board/test_board_needs.py |
| T1101 | Needs you cards had no category or effort and were not sorted easiest first | tests/board/test_board_needs.py |
| T1107 | A card could not tell Ready to ship that the live check was only partly done (no `partial` object) | tests/board/test_board_needs.py |
| T1229 | A run waiting in paused_retry with a stale Q/A tag showed in Needs you instead of Running | tests/board/test_board_status.py |
