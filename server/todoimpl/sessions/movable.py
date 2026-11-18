"""Whether a manual session may move to the board, and if not, why: one verdict for the GET row and the POST.

kuhy's rule (2026-11-18): a session with no status tag, or one still tagged `R:` that has been quiet for an
hour, has stalled and can go to the board's headless mode. `A:` and `Q:` wait for kuhy himself; done,
continuing and hand-marked sessions are finished. The board needs a repo, so the cwd must be a clone with a
GitHub `origin` the board has a clone of, unless the request names the repo (`repos` in the handoff body).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from todoimpl.sessions import origin
from todoimpl.tokens_api import paths

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.parse import Session

STALE_SECONDS = 3600
_BLOCKED = {
    "needs_action": "waits for your action (A:): answer it in its terminal",
    "question": "asks you a question (Q:): answer it in its terminal",
    "done": "already done",
    "continuing": "already done",
}

# The clock, as a seam so tests pin the one-hour rule.
now = time.time

type Verdict = tuple[str | None, str | None]  # (repo, reason it cannot move); a repo means it can


def _last_activity(session: Session) -> float:
    """Epoch of the newest prompt or reply; the transcript's mtime when the records carry no usable time."""
    try:
        return datetime.fromisoformat(session.last_ts or "").timestamp()
    except ValueError:
        return session.mtime_ns / 1e9


def status_reason(session: Session, manual: str | None) -> str | None:
    """Return why the session's status keeps it off the board, or None when it has stalled."""
    if manual == "done":
        return "already done"
    if session.status == "running" and now() - _last_activity(session) < STALE_SECONDS:
        return "still running: active in the last hour"
    return _BLOCKED.get(session.status)


def _repo_reason(repo: str) -> str | None:
    if not origin.REPO.fullmatch(repo):
        return "repo must look like owner/name"
    return None if origin.has_clone(repo) else f"no clone of {repo} for the board to run in"


def verdict(
    runner: CommandRunner, session: Session, manual: str | None, override: str | None = None
) -> Verdict:
    """Return (repo, None) when the session can move, else (None, why); git runs only for a stalled one."""
    reason = status_reason(session, manual)
    if reason is not None:
        return None, reason
    if override is not None:
        reason = _repo_reason(override)
        return (None, reason) if reason else (override, None)
    if not session.cwd or not paths.sysroot_path(session.cwd).is_dir():
        return None, f"its directory {session.cwd or '(unknown)'} no longer exists"
    repo = origin.CACHE.repo(runner, session.cwd)
    if repo is None:
        return None, f"no GitHub origin remote in {session.cwd}; the API takes the repo in `repos`"
    reason = _repo_reason(repo)
    return (None, reason) if reason else (repo, None)
