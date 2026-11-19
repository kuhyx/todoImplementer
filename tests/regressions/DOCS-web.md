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
| T1916 | A repo task's parts had no state on the card and a queued card did not say which run it waits on; the card shows an icon per part and a lock for the wait | web/src/components/repo-parts.test.ts |
| T1926 | The 10 s poll of the sessions page redrew the table while a delete was armed or a control had focus, which disarmed the delete and dropped the focus; a redraw now waits until the delete disarms or the focus leaves | web/src/sessions/app.test.ts |
| T1950 | A failed run's Needs box printed its reason twice (the need text and the run error were the same string); the error line is now skipped when it repeats the need | web/src/components/drawer.test.ts |
| T1993 | On a card holding both ask buttons and a free question, the ask slot took the question's grid row so the question title and box were not visible | web/src/components/drawer-later.test.ts |
| T2001 | A banner with a long unbreakable path (missing API key) widened the page to 484 px on a 390 px phone, so the full-screen create dialog ran off the right edge and hid Create; banners now wrap | web/src/styles/header-wrap.test.ts |
| T2077 | After the Ready to ship column went the board still split its width into five, so the four columns (and the narrow-screen tabs) filled 80 % at 4K with an empty strip on the right; the grids now split by the real column count (`--cols` set by `renderBoard`) | web/src/components/board-width.test.ts |
| T2094 | The issue links of the tracking view and the umbrella block pointed at the raw `GET /api/task/<id>/issues` ndjson, so a click downloaded a txt file; they now open the readable `/issues#task=<id>` page | web/src/track/track-parts.test.ts, web/src/components/umbrella.test.ts, web/src/issues/app.test.ts |
| T2099 | The task detail Claude log listed the oldest line first, so the latest result sat at the bottom out of sight; the web feed and the app feed now put the newest line on top | web/src/components/feed-view.test.ts, app/test/ui/live_feed_test.dart |
| T2100 | The web feed printed each HH:MM:SS in UTC (`toISOString`) instead of the viewer's timezone; it now formats in the browser timezone (the app already showed local time) | web/src/components/feed-view.test.ts |
| T2219 | The task detail now shows the card's model as a chip and draws the `model` action as a row of short model buttons (the pin pressed); a click posts `{model: id}`, a disabled picker names why | web/src/components/model-picker.test.ts |
| T2220 | The app's card sheet shows the card's model and draws the `model` action as chips (default as a glyph, the pin selected); a tap sends `task_model {model}`, the action bar no longer offers it as a bare glyph | app/test/ui/model_picker_test.dart |
| T2273 | A card resting on questions (spec questions, or a plain Claude question with an ask block) gave no way to send a free note: the only-ask stylesheet hid Send to Claude and the plain-question view took the `send` action for its answer box; the note box now stays below the questions in every mode (one Send button, answer drafts kept; T1805 now expects it) | web/src/components/drawer-compose.test.ts |
| T2274 | The Questions tab counted every spec question, so a running card whose 15 questions were all answered still read "Questions (15)" as if they were open; it now counts the unanswered ones and drops the count at zero | web/src/components/drawer-compose.test.ts |
| T2276 | The app's drawer page showed the asks with no Send to Claude, so a note needed the card sheet; it now has a note box under the asks whenever the card offers `send` (disabled one speaks why, a refused note keeps its text) | app/test/ui/detail_note_test.dart |
| T2290 | `web/dev/viewport_questions.py` probed `textarea[name]` over the whole page, so it matched the hidden New task `body` textarea before the question drawer answer box and its focus and slot checks failed (focused false, answer slot at 0); every answer probe is now scoped to `.drawer` | tests/test_viewport_questions_selectors.py |
| T2310 | The app's live-feed tab spun forever on every card: the production relay was built without the RTDB listen, so `live/{card}` (the relay does keep the last 200 events, idle cards too) never reached it; the relay now listens, and a feed with no first read after 5 s, or an empty one, shows an empty-state glyph | app/test/ui/live_feed_test.dart, app/test/sync/services_test.dart |
