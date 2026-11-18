"""Move stalled manual sessions to the board: a todo task each, its card started, the session marked done.

Approved by kuhy on 2026-11-18. The guard is the one every session mutation shares (`lookup.py`: canonical
ids of scanned sessions, cwd from the transcript), at most five ids like resume, and all-or-nothing up to the
first task: every id must be movable (`movable.py`, the verdict the GET row shows), every title new on the
board and in the batch, before anything is created. `add_task` cannot be undone, so a create failing
mid-batch reports what landed, and only the sessions that landed are marked done.

Idempotent (T2047): a session whose own task is open already (same title, its id in the body) adopts it, so
a rerun after a half-finished handoff starts that card and marks the session instead of refusing a twin.
Every task is added first and the cards are looked up after, so a batch costs one board fetch, not one each.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.sessions import api, handoff_text, mark, markstore, movable
from todoimpl.sessions.lookup import is_bulk, known_sessions, plural
from todoimpl.sessions.mark import write_marks
from todoimpl.sessions.result import MutationResult
from todoimpl.sessions.resume import MAX_BULK

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.parse import Session

_CONFLICT = "conflict"
# What became of the card's Start, per session line. WAITS: the card is held (a run on it), so it starts by
# itself when that run ships (runner/whenfree.py).
STARTED, WAITS, NOT_STARTED = "started", "starts when free", "not started"


class Board(Protocol):
    """What the handoff needs from the board: the new-task path (`NewTaskService`) and the card's Start."""

    def check_twin(self, task: NewTask) -> None:
        """Raise BackendError when the repo already has an open part with this title."""

    def adopt(self, task: NewTask, key: str) -> tuple[str, str] | None:
        """Return (note id8, card) of the open section this task became before (`key` in its body)."""
        ...

    def add(self, task: NewTask) -> str:
        """Add the task and return its note id8."""
        ...

    def card_of(self, note8: str, task: NewTask) -> str | None:
        """Return the card that holds the section, None when it never shows."""
        ...

    def start(self, card: str) -> str:
        """Press the card's Start: STARTED, WAITS (held: it starts when its run ships) or NOT_STARTED."""
        ...


def _repos(body: dict[str, object]) -> dict[str, str] | MutationResult:
    raw = body.get("repos", {})
    if not isinstance(raw, dict) or not all(isinstance(v, str) for v in raw.values()):
        return MutationResult.failure("Expected 'repos' to map session ids to owner/name.")
    return {str(k): str(v) for k, v in raw.items()}


def _over_cap(body: dict[str, object]) -> MutationResult | None:
    raw = body.get("ids")
    if not isinstance(raw, list) or len(raw) <= MAX_BULK:
        return None
    return MutationResult.refusal(
        f"At most {MAX_BULK} sessions can move at once.", stderr=f"Got {len(raw)} ids; nothing was created."
    )


def _plan(
    runner: CommandRunner, sessions: list[Session], repos: dict[str, str]
) -> list[tuple[Session, NewTask]] | MutationResult:
    """Return every session's task, or the refusal naming each session that cannot move and why."""
    marks = markstore.read_marks(api.marks_path())
    planned: list[tuple[Session, NewTask]] = []
    blocked: list[str] = []
    for session in sessions:
        manual = marks.get(session.id, {}).get("mark")
        repo, reason = movable.verdict(runner, session, manual, repos.get(session.id))
        if repo is None:
            blocked.append(f"{session.id[:8]}: {reason}")
            continue
        task = NewTask(repo, handoff_text.title(session), handoff_text.body(session), ())
        planned.append((session, task))
    if blocked:
        return MutationResult.refusal(f"Nothing moved: {'; '.join(blocked)}.", stderr="\n".join(blocked))
    twins = {(t.repo, t.title) for _, t in planned}
    if len(twins) < len(planned):
        return MutationResult.refusal(
            "Nothing moved: two sessions share the same title in one repo.", stderr="Move them one at a time."
        )
    return planned


type Entry = tuple[Session, NewTask, tuple[str, str] | None]  # the adopted (note id8, card), if any


def _resolve(board: Board, planned: list[tuple[Session, NewTask]]) -> list[Entry] | MutationResult:
    """Adopt each session's own open task; refuse a twin that belongs to someone else."""
    out: list[Entry] = []
    for session, task in planned:
        try:
            adopted = board.adopt(task, f"session {session.id}")
            if adopted is None:
                board.check_twin(task)
        except BackendError as exc:
            if exc.code == _CONFLICT:
                return MutationResult.refusal(f"Nothing moved: {exc.message}.", stderr=exc.message)
            return MutationResult.failure("Could not ask the todo app for open tasks.", stderr=exc.message)
        out.append((session, task, adopted))
    return out


def _mark_moved(moved: list[str]) -> str | None:
    """Mark the moved sessions done (the page's one mark writer); return the error, or None."""
    path = api.marks_path()
    marks = markstore.read_marks(path)
    for session_id in moved:
        marks[session_id] = {"mark": "done", "at": int(mark.now())}
    try:
        write_marks(path, marks)
    except OSError as exc:
        return f"Could not write {path}: {exc}"
    return None


type Landed = tuple[Session, NewTask, str]  # the session, its task and the note id8 holding it


def _add(board: Board, entries: list[Entry]) -> tuple[list[Landed], BackendError | None]:
    """Add every task not adopted (adopted ones keep their note); stop at the first failure."""
    landed: list[Landed] = []
    for session, task, adopted in entries:
        if adopted is not None:
            landed.append((session, task, adopted[0]))
            continue
        try:
            landed.append((session, task, board.add(task)))
        except BackendError as exc:
            return landed, exc
    return landed, None


def _move(board: Board, entries: list[Entry], *, bulk: bool) -> MutationResult:
    known = {s.id: a[1] for s, _, a in entries if a is not None}
    landed, error = _add(board, entries)
    moved: list[tuple[str, str, str]] = []  # (session id, note id8, card)
    lines: list[str] = []
    missing: list[str] = []
    for session, task, note in landed:
        try:
            card = known.get(session.id) or board.card_of(note, task)
        except BackendError as exc:
            card, why = None, exc.message
        else:
            why = "its card is not on the board yet"
        if card is None:  # the task landed: a rerun adopts it
            missing.append(f"note {note} got {session.id[:8]}'s task, but {why}")
            continue
        moved.append((session.id, note, card))
        lines.append(f"{session.id}: note {note} card {card} {board.start(card)}")
    unmarked = _mark_moved([sid for sid, _, _ in moved]) if moved else None
    stdout = "\n".join(lines)
    if error is not None and not landed and error.code == _CONFLICT:
        return MutationResult.refusal(f"Nothing moved: {error.message}.", stderr=error.message)
    if error is not None or missing:
        why = "the next one failed" if error is not None else "rerun to adopt the rest"
        summary = f"Moved {len(moved)} of {len(entries)} sessions; {why}."
        problems = [error.message if error else None, *missing, unmarked, stdout]
        return MutationResult.failure(summary, stderr="\n".join(filter(None, problems)))
    if unmarked is not None:
        return MutationResult.failure(
            "Moved to the board, but the done marks were not written.", stderr=unmarked
        )
    if bulk:
        return MutationResult.success(f"Moved {plural(len(moved))} to the board.", stdout=stdout)
    _, note, card = moved[0]
    return MutationResult.success(
        f"Moved {entries[0][1].title} to the board: note {note}, card {card}.", stdout
    )


def _checked(body: dict[str, object]) -> tuple[list[Session], dict[str, str]] | MutationResult:
    """Return the sessions and repo overrides a body names, or why it is refused."""
    refused = _over_cap(body)
    if refused is not None:
        return refused
    repos = _repos(body)
    if isinstance(repos, MutationResult):
        return repos
    sessions = known_sessions(body)
    if isinstance(sessions, MutationResult):
        return sessions
    if not set(repos) <= {s.id for s in sessions}:
        return MutationResult.failure("'repos' names a session the request does not move.")
    return sessions, repos


def apply(runner: CommandRunner, body: object, board: Board | None) -> MutationResult:
    """Hand each named session to the board's default headless mode."""
    if not isinstance(body, dict):
        return MutationResult.failure("Expected a JSON object.")
    checked = _checked(body)
    if isinstance(checked, MutationResult):
        return checked
    if board is None:
        return MutationResult.failure("The board's task service is not running; nothing moved.")
    planned = _plan(runner, *checked)
    if isinstance(planned, MutationResult):
        return planned
    entries = _resolve(board, planned)
    return entries if isinstance(entries, MutationResult) else _move(board, entries, bulk=is_bulk(body))
