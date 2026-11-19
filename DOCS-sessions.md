# Manual sessions (CHANGE 6)

kuhy asked (2026-11-11) to move the Sessions tab of control-panel here: the list of every Claude Code session he started by hand that is not done
yet. todoImpl runs headless `claude -p` sessions itself and did not track the manual ones. control-panel loses its tab in a separate commit, after
kuhy confirms parity. The page is text-free (icons and numbers; words only in `title` and `aria-label`, textgate); session titles, prompts and
replies are his own content and stay text.

## Layout

| Part | Where |
|---|---|
| Page | `/sessions` (`web/src/pages/sessions.astro`, `web/src/sessions/`), reached by the terminal icon link next to the usage link on the board |
| Scan | `server/todoimpl/sessions/` (`tags` = status tag regex, `parse`, `scan`, `markstore`, `api` = the GET body) |
| Mutations | `sessions/resume.py`, `mark.py`, `delete.py`, `handoff.py` (+ `handoff_text.py`, `movable.py`, `origin.py`), `lookup.py` (the shared id guard), `commands.py` (command seam), `router.py` (name to handler) |
| Routes | `http/sessions.py`: `GET /api/sessions`, `POST /api/sessions/<resume|mark|delete|handoff>`; contract `contracts/sessions.schema.json` |
| Tests | `tests/sessions/` (ported from control-panel), `tests/http/test_http_sessions.py`, `web/src/sessions/*.test.ts` |

## Rules carried over

- **What is listed.** Top-level `*.jsonl` of `~/.claude/projects/*/`, entrypoints `sdk-cli` and `sdk-py` skipped (the board's own runs).
  Status from the last assistant text: the long tags and the one-letter `D:` `R:` `Q:` `A:` `C:` (the regex of `~/.claude/hooks/status_tag_stop.py`,
  working-tree version of control-panel's `_status.py`), `continuing in new session` anywhere, a prompt typed after the reply makes it untagged.
  `group` is the server's urgency rank (needs_action, question, untagged, running, done or continuing); the list arrives sorted by it, newest first.
- **Marks.** `~/.claude/session-status.json`, unchanged, so existing marks carry over; written by tmp + rename.
- **Guard.** An id must be a canonical lowercase UUID of a scanned session; cwd comes from the transcript, never the request; bulk is all-or-nothing
  and one bad id refuses the lot. Resume allows at most 5 ids. Delete never unlinks: it moves to `~/.claude/projects-trash/<date>/<dir>/`, refuses
  an id written in the last 10 minutes, a symlink or a path outside `~/.claude/projects`, and an occupied trash slot.
- **Auth.** The four POSTs run after `check_post` (same-origin Origin and the CSRF token), like Ship, because this server is reachable through
  Caddy and Google sign-in; control-panel is loopback only. A refusal by the guard is HTTP 200 with `refused: true` (the guard working); bad
  JSON is 400, a bad Origin or token 403.

## Resume

Desktop: `systemd-run --user --collect --unit=claude-resume-<id8>-<epoch> --setenv=DISPLAY --setenv=XAUTHORITY terminator --working-directory=<cwd>
-x zsh -lic 'claude --resume <id>; exec zsh -i'`. DISPLAY and XAUTHORITY are read from `systemctl --user show-environment` (checked 2026-11-11:
`DISPLAY=:0`, `XAUTHORITY=/home/kuhy/.Xauthority`), so it works although `deploy/todoimplementer.service` sets neither; the unit's `PATH` has
`/usr/bin` (terminator, systemd-run). On a phone-sized viewport (CSS, max-width 700 px) the terminal buttons are hidden and the copy button stays.
Copy writes the same `cd '<cwd>' && claude --resume <id>` the board's copy-resume uses, but flashes a check on the button instead of a toast.

## Move to board

kuhy asked (2026-11-18) to hand a stalled manual session to the board's default headless mode instead of resuming it
in a terminal. Every row carries `movable` and `move_reason`, computed by the server (`sessions/movable.py`), never
by a page: a row can move when it is untagged, or tagged `R:` with no activity for an hour (`last_ts`, else the
transcript's mtime), and is not done or hand-marked; `A:` and `Q:` wait for kuhy. Its cwd must also be a clone
whose `git -C <cwd> remote get-url origin` is a github.com URL (https or ssh, read as `owner/name`, cached per cwd
for a minute) and the board must have a clone of that repo (`board/repos.py`). git runs only for rows whose status
allows a move. A disabled button carries `move_reason` as its `title` and `aria-label`.

`POST /api/sessions/handoff` takes `{"id"}` or `{"ids": [...]}` (at most 5) and an optional
`"repos": {"<id>": "owner/name"}` for a cwd with no origin, such as `$HOME`; an override needs a local clone. It
runs the same guard as the other POSTs, then refuses the whole batch if any session cannot move, if two share a
title in one repo, or if the repo already has an open part with that title (`NewTaskService.adopt`, one repo listing per session), unless
that part is the session's own earlier task (its body names the session id): then the handoff adopts it, starts
its card and marks the session, so a rerun of a half-finished handoff finishes it (T2047). Then it adds every
new task through `NewTaskService.add` and looks the cards up after (`card_of`: a read of that repo alone, laid over
the board cache, never the in-flight board fetch, which may predate the add: T2046), so a batch costs no board fetch (title = the session title on one line, at most
200 characters; body = `### what`, `### where`, `### done`, `### verify`, `### read first` with the transcript
path, kuhy's last prompt and the end of the last reply quoted line by line so no line can start a card, a fence or
a `done_check:`), presses the card's Start as `POST /api/new-task` does, and marks the session done in the marks
file. When a run holds the card (it is working, on spec questions or shipping) and Start is
refused, the card starts by itself the moment that run ships (`start_when_free`, DOCS-repotask.md, "Cycles").
A create that fails mid-batch, or a card that never shows, reports `Moved n of m` and marks only the sessions
whose card started; a rerun adopts the rest. The answer is the usual
`result`, with one `<id>: note <id8> card <card> started|starts when free|not started` line per session in
`stdout`. The page
and the app show it as a robot icon per row and in the bulk bar; the app sends `session_handoff` over the relay.

## The page

Every column sortable (status = the server's group, idle time, project, title, done mark; shift extends), group rows while unsorted, status chips
with counts, project, idle days, mark and show-done filters, fuzzy search (`usage/table-model.ts`), all in the hash (`#t.s.q`, `t.s.sort`, `status`,
`project`, `older`, `mark`, `done=1`), a 10 s poll that redraws only when the list changed, select with shift range and select-all, a bulk bar
(mark, unmark, copy commands, resume up to 5, delete), an expandable row (cwd, id, last prompt, last reply). The outcome of an action is a
check, lock (refused) or warning glyph whose `title` is the server's summary; delete is two clicks (the first arms it, red, with the count).

## Defaults chosen (not in the brief)

- `mark` (manual, tag, open) is sent by the server next to `group`, so the page derives nothing about status.
- The age is `5m`, `3h`, `12d` (numbers with a unit letter, no words).
- The cold first scan of ~2000 transcripts takes ~2.3 s (the same as control-panel); later requests ~15 ms.
- The page title is `todoImplementer`; no `noscript` text.
