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
