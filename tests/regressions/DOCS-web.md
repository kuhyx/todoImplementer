# Web regressions

Ids are global and never reused; the row's test is titled `[T<N>] ...` (vitest).

| Id | What went wrong | Test |
| --- | --- | --- |
| T601 | With no tab in the URL hash the board opened on "Needs you" even when empty, so a phone showed "Nothing in this column" above 59 backlog cards | web/src/components/active-column.test.ts |
| T801 | A live frame that failed Zod toasted only "live stage: unexpected shape": no path, no expected/received, no raw payload in the console | web/src/lib/live-feed.test.ts |
| T802 | Identical error toasts stacked: three bad frames gave three identical toasts | web/src/components/feedback.test.ts |
| T1401 | routes.shot kept only the last path segment, so nested live-check screenshots requested the wrong URL and rendered broken | web/src/lib/routes.test.ts |
