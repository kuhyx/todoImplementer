"""Move stalled manual sessions to the board: a todo task each, its card started, the session marked done.

Approved by kuhy on 2026-11-18. The guard is the one every session mutation shares (`lookup.py`: canonical
ids of scanned sessions, cwd from the transcript), at most five ids like resume, and all-or-nothing up to the
first task: every id must be movable (`movable.py`, the verdict the GET row shows), every title new on the
board and in the batch, before anything is created. `add_task` cannot be undone, so a create failing
mid-batch reports what landed, and only the sessions that landed are marked done.
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

    def create(self, task: NewTask) -> tuple[str, str]:
        """Add the task and return (note id8, the card that holds it)."""
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


def _check_twins(board: Board, planned: list[tuple[Session, NewTask]]) -> MutationResult | None:
    for _, task in planned:
        try:
            board.check_twin(task)
        except BackendError as exc:
            if exc.code == _CONFLICT:
                return MutationResult.refusal(f"Nothing moved: {exc.message}.", stderr=exc.message)
            return MutationResult.failure("Could not ask the todo app for open tasks.", stderr=exc.message)
    return None


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


def _move(board: Board, planned: list[tuple[Session, NewTask]], *, bulk: bool) -> MutationResult:
    moved: list[tuple[str, str, str]] = []  # (session id, note id8, card)
    lines: list[str] = []
    error: BackendError | None = None
    for session, task in planned:
        try:
            note, card = board.create(task)
        except BackendError as exc:
            error = exc
            break
        started = board.start(card)
        moved.append((session.id, note, card))
        lines.append(f"{session.id}: note {note} card {card} {started}")
    unmarked = _mark_moved([sid for sid, _, _ in moved]) if moved else None
    stdout = "\n".join(lines)
    if error is not None and not moved and error.code == _CONFLICT:
        return MutationResult.refusal(f"Nothing moved: {error.message}.", stderr=error.message)
    if error is not None:
        summary = f"Moved {len(moved)} of {len(planned)} sessions; the next one failed."
        return MutationResult.failure(
            summary, stderr="\n".join(filter(None, [error.message, unmarked, stdout]))
        )
    if unmarked is not None:
        return MutationResult.failure(
            "Moved to the board, but the done marks were not written.", stderr=unmarked
        )
    if bulk:
        return MutationResult.success(f"Moved {plural(len(moved))} to the board.", stdout=stdout)
    _, note, card = moved[0]
    return MutationResult.success(
        f"Moved {planned[0][1].title} to the board: note {note}, card {card}.", stdout
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
    return _check_twins(board, planned) or _move(board, planned, bulk=is_bulk(body))
