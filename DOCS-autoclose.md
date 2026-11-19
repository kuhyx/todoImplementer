# Auto close

When an open item's trusted `done_check` starts passing on its own, todoImplementer starts a **closing run**
without a click. The run closes the item itself (T2060); there is no Close click.
Code: `server/todoimpl/runner/autocheck.py` (the poll) and `runner/closing.py` (the stage, auto-start and Close).

## Switch, trust, poll

- **Switch.** The switch is `$TODOIMPL_HOME/settings.json` `{"auto_close": true}`. If the key is absent, or the file
  is missing or bad, it is off. Every tick re-reads it. While it is off, the poll runs nothing and deletes the cache,
  and the board header reads `auto close: off`. There is no endpoint for it.
- **Trust.** This is the todo-hooks rule, re-implemented read-only:
  - The trust file is `$TODO_HOOKS_TRUST_FILE`, or `~/.config/todo-hooks/trusted-checks` when that is unset.
  - The first token of each line is a hash. `#` lines are skipped.
  - The hash is `sha256(done_check.strip().encode())`.
  - If the file is missing or unreadable, nothing is trusted. Deleting a line stops that item on the next tick.
- **Poll.**
  - It runs every 5 min. The first tick runs right at startup.
  - It runs one check at a time on one thread, so ticks never overlap.
  - Each check runs as `capped.sh bash -c <check>` with a 60 s timeout. The working directory is the item's repo
    main checkout, and no worktree is made.
  - It polls only open items that have a trusted check and either no run, or a failed/cancelled closing run.
  - The item's check follows the `items.py` rule: the item's own check, or the note's check when the note has one
    item.
- **Cache.** The cache is `$TODOIMPL_HOME/autocheck.json`:
  `{item id: {at, passed, trusted, reason, pending}}`. Each tick rewrites it atomically, and it survives restarts.
- **Baseline.** If a tick runs with the switch on and finds no cache file, it records a baseline. Items already
  passing then are not started; their note is "passes, auto skipped (baseline)". They keep their normal Start.

## When a run starts

- **Trigger.** A trusted, passing item starts a run when two things hold:
  - it was seen red, or it is new after the baseline;
  - it has no `state.json`.
- **Atomic start.** The start is `Scheduler.auto_start`. It takes the same lock as Start, and inside that lock it
  checks again that the item has no run. Whichever start arrives second does nothing, and a Start click that lost
  the race returns the card without an error.
- **Usage limit.** While a limit is active, a pass sets `pending` and the start waits for the next tick; it is never
  dropped.
- **Never automatic.** A failed or cancelled run never restarts by itself.

## The closing run

| From | To | Trigger | Kind |
|---|---|---|---|
| (no run) | closing | auto close: a trusted done_check turned green | auto |
| closing | gate | closing turn ends and the server's done_check re-run is green (else failed) | auto |
| gate (closing run) | closed | close: re-run green and close_task done (else failed) | click |
| failed, cancelled (closing run) | closing | start again, only while the latest poll saw the check pass | click |

- **No worktree.** The run has no worktree. Its `state.json` carries `auto_start: {reason: "done_check", passed_at}`,
  which the card shows as `auto: done_check passed at <time>`. It is kept after Close.
- **`closing` stage.**
  - One Sonnet turn runs with role `closing`. Its working directory is the repo main checkout, `Edit`, `Write` and
    `NotebookEdit` are denied, and the prompt forbids edits.
  - Then the server re-runs the check itself, with the 600 s timeout.
  - Green: the run closes the item at once (below); no gate, no Close button, no Ship.
  - Red: the run fails with `checks_failed`.
- **Close** (`closing_stage`, no click).
  - Green re-run: `close_task` runs with the evidence (the check and its output tail, plus the closing turn's
    reply), and the stage becomes `closed` (status `done`).
  - The todo app refuses: the run goes to `failed` ("Closing the item failed: ...") and the item stays open.
  - A run found at `gate` when the server starts (an older server left it) closes at once without a second turn
    (`close_only`).
- **After a failure.** Start restarts into `closing`, but only while the latest poll saw the check pass. Send is
  disabled with "closing runs take no notes; Start again or Cancel".
- **Cancel.** Cancel abandons the note when no other section is open; the poll then skips it, and Restart is
  disabled with "the note is abandoned: auto close no longer polls its done_check".

## The card's `auto` note

The note appears on backlog cards that have no run, only while the switch is on. It holds the latest poll reason
from the server:

- untrusted check (not in trusted-checks)
- note-level check ignored (multi-item note)
- no repo checkout
- check timed out
- waiting for a pass
- passes, auto skipped (baseline)
- passes, auto start deferred (usage limit)
