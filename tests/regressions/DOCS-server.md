# Server and gate regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...` (pytest) or titled
`[T<N>] ...` (vitest); `scripts/check_regressions.py` fails on a row without a test or a tag without a row.

| Id | What went wrong | Test |
| --- | --- | --- |
| T101 | `service._act` let the runner's RunnerError(message, code) escape, so every refusal (not_found, conflict, disabled, bad_request) became HTTP 500 | tests/service/test_service_errors.py |
| T102 | Scheduler stage/done events carried only `{type, stage}` / `{type}`, so SSE payloads failed contracts/live.schema.json (no status, column, current, needs, actions) | tests/service/test_service_live.py |
| T103 | Once every section of a note was shipped the note closed, `list_tasks` stopped returning it and its shipped cards vanished from /api/board (Done column always empty) | tests/service/test_service_closed.py |
| T104 | The /api/live connect snapshot of a card never run sent `stage: null`, which live.schema.json and its Zod mirror rejected, so opening any backlog card toasted "live stage: stage: Invalid option" | tests/http/test_http_live.py, web/src/lib/live-feed.test.ts |
| T1862 | A card's body came live from the source note, so once the note was rewritten (split into new notes) or closed the card lost the text its run was started from | tests/board/test_board_note_body.py, tests/runner/test_runner_note_body.py |
| T901 | After a restart every recovered run landed in Needs you with "unknown task <card>": build_backend started the Scheduler (whose recovery drives call get_task) before the first note fetch filled the cache | tests/service/test_service_build.py |
| T1402 | Task repo "kuhyx/todo-app" showed Start disabled "repo ~/src/todo-app not found": repo_path ignored checkouts whose directory name differs from the repo name (~/src/todo) | tests/board/test_board_repo_path.py |
| T1100 | A claude_action/claude_question card showed the generic "see the feed" text instead of the session's last `A:`/`Q:` line | tests/board/test_board_needs.py |
| T1101 | Needs you cards had no category or effort and were not sorted easiest first | tests/board/test_board_needs.py |
| T1107 | A card could not tell Ready to ship that the live check was only partly done (no `partial` object) | tests/board/test_board_needs.py |
| T1229 | A run waiting in paused_retry with a stale Q/A tag showed in Needs you instead of Running | tests/board/test_board_status.py |
| T1800 | A usage-limit pause disabled Send answers and Spec OK, so kuhy could not answer a spec question until the limit ended | tests/board/test_board_limit_answers.py |
| T1804 | Effort bucketed open questions (1-3 all scored 1, 9-20 all scored 3), so a 1-question card did not sort above a 3-question one | tests/board/test_board_needs.py |
| T1807 | After a reboot the board resumed a run before the todo MCP was up; the empty cache read as "unknown task" and failed the run instead of retrying | tests/service/test_service_view.py |
| T1812 | A retried follow-up could add the same section twice after a lost add_task reply | tests/service/test_service_view.py |
| T1811 | Least effort put a 9-question card after criteria-not-done cards; every question card must come first | tests/board/test_board_needs.py, web/src/lib/board-model.test.ts |
| T1815 | A cancelled card sat in Backlog as a to-do and its note stayed open; Cancel now abandons the note where it can and the card shows Abandoned under Done | tests/board/test_board_status.py, tests/service/test_service_view.py, tests/runner/test_runner_abandon.py |
| T1921 | Cancel on an umbrella card abandoned the whole umbrella note through the T1815 path, because the note is one card with no other open section; an umbrella note now stays open on Cancel, its children with it | tests/service/test_service_umbrella.py |
| T1835 | A Needs-you card said "Claude needs you to do something: see the feed" (or another generic line) while the reply had an `N:` line, a question round or a last paragraph naming the ask | tests/board/test_board_needs_ask.py |
| T1880 | A worktree holding a non-UTF-8 file made `/api/task/<id>` answer HTTP 500 (strict decode of `git diff`) | tests/board/test_board_diff.py |
| T1881 | The todo MCP added a trailing `created_by` column to list lines and every `/api/board` answered 502 "malformed list line" | tests/todo_mcp/test_parse.py |
| T1908 | Every GET /api/board re-parsed every stream file of every run for the skills list (137k events, 4 s under load), so the board looked down after a deploy; an unchanged stream is now parsed once (cache per mtime and size) | tests/lessons/test_lessons_streams.py |
| T1895 | The merge classifier re-sent every open note, with its first 300 characters, to Haiku each time the id set changed (a closed note or one new note meant the whole backlog again); it now classifies only new or edited notes against a short view of the stored groups and ungrouped titles, a removal alone asks nothing, and merge.json keeps a hash per note (an old file gets one full run) | tests/merge/test_merge_incremental.py |
| T1911 | A repo with several notes and sections showed one card per section, and the cards ran in parallel worktrees of the same repo and fought; the repo is now ONE card whose open sections are its parts | tests/repotask/test_group.py |
| T1912 | Ship closed the whole card or nothing: a repo task closes only the sections its run ticked and puts one `Todo:` trailer per ticked part's note | tests/repotask/test_flow.py |
| T1913 | An umbrella child and the repo's own task (or two children of one repo) worked on one repo at the same time; one run at a time per repo now, and the queued card names the run it waits on | tests/repotask/test_locks.py, tests/repotask/test_umbrella_lock.py |
| T1914 | The move to repo tasks could lose or restart per-section runs: a run in flight keeps its own card and its section stays out of the repo run, and no new section-level run starts | tests/repotask/test_legacy.py |
| T1915 | A repo kept several open notes in the todo app, against the rule one repo = one note; the migration merges them (dry run first), skips notes with a run in flight and never closes a note whose sections did not arrive | tests/repotask/test_migrate.py |
| T1951 | A MANUAL WORK REQUIRED card with a repo read "yours: no repo on this note" and never said what kuhy must do; it now shows the `Needs:` lines of its manual note or human parts, or says the note has none | tests/repotask/test_board.py |
| T1992 | A repo card's body is empty (its text lives in its parts), so an ask block written in a part never reached the card | tests/asks/test_asks_parts.py |
| T1994 | A MANUAL WORK REQUIRED card kept Start disabled after kuhy answered every ask in it, so a decided task could never run; a manual part whose asks are all resolved is now Claude's work on the same card (Start enabled) and its prompt carries kuhy's answers | tests/repotask/test_released.py |
