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
| Board | open `/` -> four columns Backlog / Running / Needs you / Done (a shipping card is in Running) | every open todo item is one card, grouped by repo, kuhy's own notes above Claude-made ones in each column; GET `/api/board` matches `contracts/board.schema.json` |
| Yours lane | notes with no `repo` (the board reads them with `list_tasks(no_repo: true)`, T2058) | shown in "Yours", never startable; a note added in the todo app is a Backlog card on the next refresh (2 s after the last fetch ended) |
| Triage | a note with no `repo` and no run; `tests/triage` | Haiku labels it once per text (`<run dir>/triage.json`): `existing_repo` sets the note's repo (the card joins that repo's), `all_repos` rewrites the note into an umbrella (one child per repo whose clone has the literal), `new_repo` and `research` become Backlog cards with Start, `manual` stays Yours; the card shows the label as an icon (DOCS-triage.md) |
| New repo | Start on a `new_repo` card | creates private `kuhyx/<name>`, pushes a scaffold, clones it to `~/src/<name>`, sets the note's repo, starts the repo's card (`newrepo.json` resumes a cut run; a failure is a failed run with Retry) |
| Research | Start on a `research` card | Sonnet session with no repo writes `research.md` (drawer report), ends on one Make note / Skip choice per suggested action; picked actions become todo notes, the note closes |
| Start | card -> Start (POST `/api/task/<id>/start`) | card leaves Backlog; at most 3 run at once, the rest are queued |
| Spec Q&A | card in Needs you with `❓ Qn` cards -> answer -> Spec OK | answers reach the session, Plan starts |
| Live feed | open a card drawer (GET `/api/live?id=<id>`, SSE) | first frame is a stage snapshot, then activity/stage/cost events |
| Send to Claude | drawer -> text box -> Send (POST `.../send`) | text is the next turn of the same session; on a Needs-you card with no session yet it restarts the run with the text as kuhy's note |
| Resume command | drawer -> "copy resume command" | `cd <worktree> && claude --resume <id>` on the clipboard |
| Plan + live check | automatic after Start | `plan.md` and `live_check.md` in the run dir; checks tail in `/api/task/<id>` |
| Gate | a green card (plan, live check, checks) | no rest and no click (T2060): the card goes straight to Ship, shown as Shipping in Running |
| Ship | automatic at the gate | one commit with `Todo: <id8>` trailer pushed to origin, section marked `## [x]`, note closed with its last item, worktree removed |
| Cheap tier | note with a `Tier: cheap` line or the title `text-free (textgate-rework)` | implement role runs on Sonnet (free models via claude-free on public repos, else alone), `ESCALATE:` or a failed turn moves it to Opus once; card icons for cheap / free / escalated (`DOCS-tiers.md`) |
| Cancel | drawer action | run stops, run dir kept |
| Done manually | any card that is not Done -> drawer / app action (confirm) (POST `.../done-manually`) | no Claude turn: a live session stops, every note behind the card is closed as done in the todo app, the card rests in Done with status `done_manually`; the reverse (a note marked done in the todo app) does the same within seconds (`DOCS-manual.md`) |
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
| F2 | start x3: three cards run in parallel worktrees and ship themselves (<= 3 at once, plan.md + live_check.md) | `tests/e2e/run_flow.py step 3-4` (rerun step 4 on exit 3) | never |
| F3 | spec Q&A: questions as cards, answers, Spec OK starts Plan | no e2e yet (needs a seeded note without done_check + a scripted grilling turn); unit gates: `capped.sh uv run --frozen pytest -q tests/board/test_board_actions.py tests/prompts -k spec` | gap |
| F4 | live feed: SSE opens with a stage snapshot while runs work | `tests/e2e/run_flow.py step 3` (reads the first `/api/live` frame) | never |
| F5 | ship: commits with trailers on the bare remote, notes closed in the fake MCP, worktrees removed | `tests/e2e/run_flow.py step 5` then `step 6` to tear down | never |

Full run: `step 1`, `step 2`, `step 3`, `step 4` (repeat while exit 3), `step 5`, `step 6`. On failure a step prints
`FAIL F1 step <i>/6: <what was expected, what was seen>; artefacts: <path>; work dir <path>` and exits 1; the
work dir stays so the run can be inspected (`step 6` removes it).

A note's repo `owner/name` runs in `~/src/<name>` or the `~/src` checkout whose origin is that repo. A `kuhyx/` repo or bare name needs only the clone; any other owner needs the origin to match (`board/repos.py` `is_clone_of`).
