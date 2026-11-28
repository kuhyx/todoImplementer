# Priority, the Backlog order and the Start confirm

T2583. Who goes first inside a card and in the queue (kuhy's parts, then the board's, then other apps'
reports): `DOCS-repotask.md`, "Parts" (T2580, T2581); other apps' reports: `DOCS-errors.md` (T2582).

kuhy, 2026-11-27: "change tasks priority; tasks in backlog ordered by priority; starting a task with lower priority
than at least one task still in backlog pops a modal asking if they are sure".

- Every open card offers the `priority` action (`board/prioaction.py`): choices high, medium, low, `value` the card's
  priority. `POST /api/task/<id>/priority {priority}` (relay kind `task_priority`) sets it on every note behind the
  card that holds an open part of kuhy's or the board's (`service/priorities.py`); a plain card is its one note. A card
  of only other apps' reports offers it disabled ("always run last; Start runs them now").
- Backlog is one list on the page and in the app: priority first (high, medium, low), then kuhy's cards before the
  board's and other apps' at the same priority (`lane`); the picked sort only breaks ties. Other columns keep it.
- An enabled Start of a card while a Backlog card of higher priority waits carries `waits: {id, title, priority}`
  (`board/outrank.py`, the highest such card), on the board and in the task detail. The page opens a modal
  ("Start anyway?", that card's priority glyph and title; Back, Start anyway); the app opens a dialog with the same
  card and glyph buttons. Nothing is sent until kuhy confirms; the server itself never refuses such a Start.

## The note check on Start (kuhy, 2026-11-28)

`board/precheck.py`, no LLM, run inside `board/actions.py` so the card's Start and the POST refusal share one reason.
A first Start (not Restart, Retry or Hand back) is disabled with the reason when the note has no done line
(`Done:`, `Done when`, `Done means`, `Success:`, `Verify:`, `Acceptance:` at a line start, or a `- [ ]` line; a
`done_check` on the card or a part counts), or the body is over 20000 characters, or a card has over 30 open parts.
The repo check is the existing one (`repo ... not found`); a repo-less note passes it because Start routes it to triage.
Exempt from the done-line rule: `created_by` claude, umbrellas, error tickets and token optimizations
(`Error-Signature:`, `Reset-Key:`) and repo-less notes labelled `research`. Size applies to every card.
