# Done manually, both ways (T2064, T2065)

kuhy, 2026-11-19: a "done manually" click moves a card to Done with no Claude turn and marks its notes done in the
todo app; a note marked done in the todo app moves its card to Done on its own. Status `done_manually`, stage
`done_manually`, action `done-manually`: told apart from `shipped`. Code: `service/dropping.py` (click),
`runner/stopping.py` (stop and rest), `service/notedone.py` (the other direction), `service/view.py` (`done_manually`).

## The click: `POST /api/task/<card>/done-manually`

Offered on every card that is not Done or Done manually, with confirm (the app: long press, glyph `done_all`).
Disabled while the run is `shipping` ("shipping cannot be stopped"): a push in flight is never cut. In order:

1. Close every note the card covers, through the todo MCP's `close_task` (the path Ship uses, `close_item`): the
   repo card's parts but a held one (a held part has its own card; the manual `-1` card's parts count), or the
   card's one section. A section is marked `## [x]`, a note closes with its last section, an umbrella note closes
   whole. Any refusal stops here, before the run is touched.
2. Stop the run without a turn: a queued run leaves the queue, a live drive is cancelled, a turn no drive follows
   is stopped. Nothing is abandoned (Cancel would reopen the note as abandoned) and no `claude` starts.
3. Rest the run at stage `done_manually`. A live drive saves the state it loaded when its cancel lands, so the click
   writes `<run dir>/done-manually.json` first and `Scheduler.after_drive` sets the stage once the drive ended
   (`Scheduler.after_recover` settles a file a restart cut). A card with no run gets a run dir with only this stage:
   it is the memory that keeps the Done card (`ClosedNotes`, also for a repo task).

The worktree stays; nothing is pushed or deployed. A repo task whose parts reappear (a new part) is Backlog again
like after a shipped cycle (`status.CYCLE_ENDS`); Start begins the next cycle. The click is an intervention
(`interventions.jsonl`, kind `done_manually`).

## The other direction: a note done in the todo app

The todo app lists open notes only, so a done note used to leave the board (a run on it went on). `NoteDoneWatcher`
(its own thread, 2 s, after each cache refresh) finds the cards that left the board and asks `get_task` per note;
`done` (or a `## [x]` section) counts, `abandoned` does not.

- Candidates: cards of the previous snapshot that are gone, and run dirs with no card and a live-ish stage (so a
  restart loses nothing). A failed run an open note still names is a part of the repo card: left alone.
- A single-note card goes to Done manually and its session stops (the same `Scheduler.done_manually`). A card with
  parts loses a part when its note is done; once every part is done it goes to Done manually. A part never stops
  the run.
- Never touched: a run that is `shipping` or closing, a note this process closed itself (`TodoClient.closed_here`:
  Ship, merge, migrate, the API key monitor), a failed refresh. Notes are never reopened or deleted.
- Asked at most 10 cards per tick; a card whose note is still open is asked again after 60 s; an unanswered one
  is retried at the next snapshot. Cards of the snapshot before a restart that closed meanwhile are only found
  when they have a run dir.
