"""Per-item run state (`<root>/<item id>/state.json`, item id `<id8>-<n>`): dataclasses, parsing, atomic save.

The runner writes it, the board reads it. Keys the board does not know are kept in `extra` so an older reader
survives a newer writer and a load/save cycle never drops them.
"""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parse import StateError, choice, item, listed, opt, opt_choice, typed

STAGES = (
    "spec",
    "spec_wait",
    "plan",
    "implement",
    "live_check",
    "checks",
    "gate",
    "shipping",
    "shipped",
    "closing",
    "closed",
    "failed",
    "paused_limit",
    "paused_retry",
    "cancelled",
)
ASSIGNEES = ("human", "claude")
TAGS = ("Q", "A", "R", "D")
FILE = "state.json"
NOTE_BODY_MAX = 20_000


@dataclass
class SpecQuestion:
    """Claude's open question with its recommended answer; `answer` is None until kuhy answers."""

    id: str
    title: str
    body: str = ""
    recommendation: str = ""
    answer: str | None = None


@dataclass
class RunState:
    """Everything the runner records about one task's run."""

    task_id: str
    stage: str
    assignee: str = "claude"
    session_id: str | None = None
    worktree: str | None = None
    branch: str | None = None
    cost_usd: float = 0.0
    spec_questions: list[SpecQuestion] = field(default_factory=list)
    last_tag: str | None = None
    error: str | None = None
    updated: float = 0.0
    repo: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    started_at: float | None = None
    resume_at: float | None = None
    auto_ship: bool = False
    sessions: dict[str, Any] = field(default_factory=dict)
    self_check: list[dict[str, Any]] = field(default_factory=list)
    checks: dict[str, Any] | None = None
    live_check: dict[str, Any] | None = None
    skills_loaded: list[str] = field(default_factory=list)
    lesson: dict[str, Any] | None = None
    ship: dict[str, Any] | None = None
    auto_start: dict[str, Any] | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    note_body: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def open_questions(self) -> list[SpecQuestion]:
        """Return the questions still without an answer."""
        return [q for q in self.spec_questions if q.answer is None]

    @property
    def closing(self) -> bool:
        """Return True for a closing run: started by a passing done_check, no worktree, ends in Close."""
        return self.auto_start is not None

    def to_dict(self) -> dict[str, Any]:
        """Return the state.json object (required keys always, optional ones when set)."""
        out: dict[str, Any] = dict(self.extra)
        out.update(
            task_id=self.task_id,
            stage=self.stage,
            assignee=self.assignee,
            session_id=self.session_id,
            worktree=self.worktree,
            branch=self.branch,
            cost_usd=self.cost_usd,
            spec_questions=[vars(q).copy() for q in self.spec_questions],
            last_tag=self.last_tag,
            error=self.error,
            updated=self.updated,
        )
        optional = {
            "repo": self.repo,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "started_at": self.started_at,
            "resume_at": self.resume_at,
            "checks": self.checks,
            "live_check": self.live_check,
            "lesson": self.lesson,
            "ship": self.ship,
            "note_body": self.note_body,
            "auto_start": self.auto_start,
        }
        out.update({key: value for key, value in optional.items() if value is not None})
        listed = {
            "sessions": self.sessions,
            "self_check": self.self_check,
            "skills_loaded": self.skills_loaded,
            "stages": self.stages,
        }
        out.update({key: value for key, value in listed.items() if value})
        if self.auto_ship:
            out["auto_ship"] = True
        return out

    @classmethod
    def from_dict(cls, data: object) -> RunState:
        """Parse a state.json object; raise StateError naming the first bad field."""
        if not isinstance(data, dict):
            msg = "state.json is not a JSON object"
            raise StateError(msg)
        known = set(cls.__dataclass_fields__) - {"extra"}
        kwargs: dict[str, Any] = {
            "task_id": typed(data, "task_id", str),
            "stage": choice(data, "stage", STAGES),
            "assignee": choice(data, "assignee", ASSIGNEES),
            "session_id": opt(data, "session_id", str),
            "worktree": opt(data, "worktree", str),
            "branch": opt(data, "branch", str),
            "cost_usd": float(typed(data, "cost_usd", (int, float), 0.0)),
            "spec_questions": [
                item(SpecQuestion, "spec_questions", q) for q in listed(data, "spec_questions")
            ],
            "last_tag": opt_choice(data, "last_tag", TAGS),
            "error": opt(data, "error", str),
            "updated": float(typed(data, "updated", (int, float), 0.0)),
            "repo": opt(data, "repo", str),
            "base_sha": opt(data, "base_sha", str),
            "head_sha": opt(data, "head_sha", str),
            "started_at": opt(data, "started_at", (int, float)),
            "resume_at": opt(data, "resume_at", (int, float)),
            "auto_ship": typed(data, "auto_ship", bool, False),  # noqa: FBT003
            "sessions": typed(data, "sessions", dict, {}),
            "self_check": listed(data, "self_check"),
            "checks": opt(data, "checks", dict),
            "live_check": opt(data, "live_check", dict),
            "skills_loaded": listed(data, "skills_loaded"),
            "lesson": opt(data, "lesson", dict),
            "ship": opt(data, "ship", dict),
            "auto_start": opt(data, "auto_start", dict),
            "stages": listed(data, "stages"),
            "note_body": clip_body(opt(data, "note_body", str)),
        }
        kwargs["extra"] = {k: v for k, v in data.items() if k not in known}
        return cls(**kwargs)


def clip_body(body: str | None) -> str | None:
    """Return the note text cut to NOTE_BODY_MAX, so an oversized note never fails a load."""
    return None if body is None else body[:NOTE_BODY_MAX]


def run_root() -> Path:
    """Return the run root: `$TODOIMPL_HOME` or `~/.cache/todoImplementer`."""
    home = os.environ.get("TODOIMPL_HOME")
    return Path(home) if home else Path.home() / ".cache" / "todoImplementer"


def run_dir(root: Path, task_id: str) -> Path:
    """Return the run dir of an item (its full `<id8>-<index>` id)."""
    return root / task_id


def load(directory: Path) -> RunState | None:
    """Return the state in a run dir, None when there is none; raise StateError when it is unreadable."""
    path = directory / FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return RunState.from_dict(json.loads(text))
    except json.JSONDecodeError as exc:
        msg = f"state.json is not valid JSON: {exc}"
        raise StateError(msg) from exc


def save(directory: Path, state: RunState) -> None:
    """Write state.json atomically (tmp file + os.replace) while holding an exclusive flock."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
    with (directory / ".state.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tmp = directory / f".{FILE}.{os.getpid()}.tmp"
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(directory / FILE)
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def load_runs(root: Path, task_ids: list[str]) -> dict[str, RunState]:
    """Return the run of every task that has one; an unreadable state becomes a failed run saying why."""
    runs: dict[str, RunState] = {}
    for task_id in task_ids:
        try:
            run = load(run_dir(root, task_id))
        except StateError as exc:
            run = RunState(task_id=task_id, stage="failed", error=str(exc))
        if run is not None:
            runs[task_id] = run
    return runs
