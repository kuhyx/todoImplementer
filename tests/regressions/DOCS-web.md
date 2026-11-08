# Web regressions

Ids are global and never reused; the row's test is titled `[T<N>] ...` (vitest).

| Id | What went wrong | Test |
| --- | --- | --- |
| T601 | With no tab in the URL hash the board opened on "Needs you" even when empty, so a phone showed "Nothing in this column" above 59 backlog cards | web/src/components/active-column.test.ts |
| T801 | A live frame that failed Zod toasted only "live stage: unexpected shape": no path, no expected/received, no raw payload in the console | web/src/lib/live-feed.test.ts |
| T802 | Identical error toasts stacked: three bad frames gave three identical toasts | web/src/components/feedback.test.ts |
| T1401 | routes.shot kept only the last path segment, so nested live-check screenshots requested the wrong URL and rendered broken | web/src/lib/routes.test.ts |
| T1105 | The board could not order Needs you by the server's effort, easiest first | web/src/lib/board-model.test.ts |
| T1106 | A card showed neither its needs category nor the partial live-check outcome | web/src/components/board.test.ts |
| T1801 | With spec-answers disabled (usage limit) a questions card fell back to a read-only stacked list of every question instead of one question with its prefilled box and OK | web/src/components/ask-disabled.test.ts |
| T1802 | Least effort still grouped cards by repo, so the easiest card overall was not at the top of its column | web/src/lib/board-model.test.ts, web/src/components/board.test.ts |
| T1803 | A Needs-you card printed the same ask twice (current line and needs quote) | web/src/components/board.test.ts |
| T1805 | A plain Claude question still showed the old free-text card and Send button instead of the one-question view, and could not be answered during a usage limit | web/src/components/ask-free.test.ts, web/src/components/drawer-free.test.ts |
| T1806 | The answer view moved title, question, answer and Back/OK with text length and sat in a side panel instead of the middle of the browser | web/src/components/drawer-free.test.ts, web/dev/viewport_questions.py |
| T1816 | A Claude question asked after every spec question was answered opened on Activity: the old answered spec cards hid it, and its ❓ cards never reached the page | tests/board/test_board_asks.py, web/src/components/drawer-later.test.ts |
