# FEATURES: todoImplementer

> Feature map + core-flow ground truth (skill: `e2e-ground-truth`). A user-visible change updates its row in the
> same commit.

- **Primary target:** web, `http://127.0.0.1:8786` (phone layout 390x844), later `https://agents.kuhy.duckdns.org`
- **Driver:** the real server (`python -m todoimpl.http.main`, detached via `systemd-run --user --collect`) driven over HTTP by
  `tests/e2e/run_flow.py`; scratch repo + local bare origin, fake todo MCP, fake `claude`, `git push` shim
- **Run one flow:** `tests/e2e/run_flow.py step <n|a-b>`, one step per call (each < 60 s; exit 0 pass, 1 FAIL, 3 still running: rerun)
- **Real-claude smoke (manual, once):** `tests/e2e/run_flow.py step 1 --real-claude`, then steps 2-6 (haiku, one item)
- **Artefacts:** `~/data/claude-scratch/e2e/todoImplementer/<timestamp>-<pass|fail-stepN>/` (server log, board JSON, claude calls)

## Feature map

| feature | how to reach it | expected outcome |
|---|---|---|
| Board | open `/` -> five columns Backlog / Running / Needs you / Ready to ship / Done | every open todo item is one card, grouped by repo, kuhy's own notes above Claude-made ones in each column; GET `/api/board` matches `contracts/board.schema.json` |
| Yours lane | notes with no `repo` (the board reads them with `list_tasks(no_repo: true)`, T2048) | shown in "Yours", never startable; a note added in the todo app is a Backlog card on the next refresh (4 s after the last fetch ended) |
| Start | card -> Start (POST `/api/task/<id>/start`) | card leaves Backlog; at most 3 run at once, the rest are queued |
| Spec Q&A | card in Needs you with `❓ Qn` cards -> answer -> Spec OK | answers reach the session, Plan starts |
| Live feed | open a card drawer (GET `/api/live?id=<id>`, SSE) | first frame is a stage snapshot, then activity/stage/cost events |
| Send to Claude | drawer -> text box -> Send (POST `.../send`) | text is the next turn of the same session; on a Needs-you card with no session yet it restarts the run with the text as kuhy's note |
| Resume command | drawer -> "copy resume command" | `cd <worktree> && claude --resume <id>` on the clipboard |
| Plan + live check | automatic after Start | `plan.md` and `live_check.md` in the run dir; checks tail in `/api/task/<id>` |
| Gate | card in Ready to ship -> drawer | plan, diff, live-check report, checks tail; Ship and Send offered |
| Ship | drawer -> Ship (POST `.../ship`) | one commit with `Todo: <id8>` trailer pushed to origin, section marked `## [x]`, note closed with its last item, worktree removed |
| Cheap tier | note with a `Tier: cheap` line or the title `text-free (textgate-rework)` | implement role runs on Sonnet (free models via claude-free on public repos, else alone), `ESCALATE:` or a failed turn moves it to Opus once; card icons for cheap / free / escalated (`DOCS-tiers.md`) |
| Cancel | drawer action | run stops, run dir kept |
| New task | toolbar + -> repo (board repos or typed `owner/name`), title, details, any files (picker/camera, paste, drop; 100 MB each, 500 MB total) -> create (POST `/api/upload` per file, then `/api/new-task`) | a `## title` section in the repo's note links the files on dufs (images inline), the repo card starts (or keeps working) and opens; sessions read run-dir copies of the files (`DOCS-repotask.md`) |
| Free credits fallback | board toggle (POST `/api/settings/credits-fallback`) | while the plan limit is active, turns run on free API credits; card badge "free credits" |
| Lessons | gate rejection -> drafted lesson -> Approve | lesson written into the named skill via `skill_lesson.py` |
| Usage | header (GET `/api/usage`) | per-task cost, plan limit state, reset time |
| Manual sessions | terminal icon link in the header -> `/sessions` (GET `/api/sessions`, POST `/api/sessions/<resume\|mark\|delete>`) | hand-started Claude Code sessions not done yet, grouped by status tag (headless runs hidden); resume opens terminator (a copy button on a phone), mark done writes `~/.claude/session-status.json`, delete moves to `~/.claude/projects-trash`; POSTs need Origin + CSRF (`DOCS-sessions.md`) |
| Pair a phone | QR icon in the header, shown only on the PC (page carries `<meta name="todoimpl-local" content="1">`) -> POST `/api/pair` | modal with the QR of a one-time link, a countdown ring with the seconds left, a fresh code when it expires; Esc, backdrop or the X closes it; a failed mint shows a warning glyph (its title is the error, tap retries) |
| Install app | install icon in the header, shown only when Chrome fires `beforeinstallprompt` and the page is not standalone | tap shows Chrome's install dialog; the icon goes away after `appinstalled`; `/manifest.webmanifest` + `/icons/*.png`, no service worker |
| Build id | GET `/version` | `{build, version}`; the page reloads when `build` changes |
| CSRF | every POST | needs same-origin `Origin` + `X-Todoimpl-Token` (the single `todoimpl-csrf` meta tag of `/`) |

## Core flows

| id | goal | command | last green |
|---|---|---|---|
| F1 | board view: every open item is a Backlog card grouped by repo | `tests/e2e/run_flow.py step 1-3` (step 3 starts with the board asserts) | never (server wiring unfinished, 2026-11-05) |
| F2 | start x3: three cards run in parallel worktrees to ready_to_ship (<= 3 at once, plan.md + live_check.md + checks tail) | `tests/e2e/run_flow.py step 3-4` (rerun step 4 on exit 3) | never |
| F3 | spec Q&A: questions as cards, answers, Spec OK starts Plan | no e2e yet (needs a seeded note without done_check + a scripted grilling turn); unit gates: `capped.sh uv run --frozen pytest -q tests/board/test_board_actions.py tests/prompts -k spec` | gap |
| F4 | live feed: SSE opens with a stage snapshot while runs work | `tests/e2e/run_flow.py step 3` (reads the first `/api/live` frame) | never |
| F5 | ship: commits with trailers on the bare remote, notes closed in the fake MCP, worktrees removed | `tests/e2e/run_flow.py step 5` then `step 6` to tear down | never |

Full run: `step 1`, `step 2`, `step 3`, `step 4` (repeat while exit 3), `step 5`, `step 6`. On failure a step prints
`FAIL F1 step <i>/6: <what was expected, what was seen>; artefacts: <path>; work dir <path>` and exits 1; the
work dir stays so the run can be inspected (`step 6` removes it).

A note's repo `owner/name` runs in `~/src/<name>` or the `~/src` checkout whose origin is that repo. A `kuhyx/` repo or bare name needs only the clone; any other owner needs the origin to match (`board/repos.py` `is_clone_of`).
