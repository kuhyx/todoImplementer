"""Shared rig of the handoff tests: a fake board and six untagged sessions in a clone of kuhyx/demo."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import sessfix as fx
from sessrunner import FakeRunner, ok
from todoimpl.http.backend import BackendError
from todoimpl.sessions import api, handoff, mark, movable

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.http.newtask import NewTask

SIDS = [f"{n}{n}{n}{n}{n}{n}{n}{n}-2222-4333-8444-555555555555" for n in range(1, 7)]
HOME_CWD = fx.HOME


class FakeBoard:
    """Records what the handoff asked of the board; `twins` are (repo, title) pairs already open."""

    def __init__(self) -> None:
        self.created: list[NewTask] = []
        self.started: list[str] = []
        self.twins: set[tuple[str, str]] = set()
        self.fail_at: int | None = None
        self.fail = BackendError("upstream_unavailable", "todo MCP is down")
        self.twin_error: BackendError | None = None
        self.outcome = handoff.STARTED
        self.adoptable: dict[tuple[str, str, str], tuple[str, str]] = {}  # (repo, title, key) -> (note, card)
        self.hidden: set[str] = set()  # notes whose card never shows
        self.broken: set[str] = set()  # notes whose card lookup fails

    def adopt(self, task: NewTask, key: str) -> tuple[str, str] | None:
        if self.twin_error is not None:
            raise self.twin_error
        found = [
            v for (r, t, k), v in self.adoptable.items() if (r, t, k in key) == (task.repo, task.title, True)
        ]
        if found:
            return found[0]
        # what an earlier call created: its body names the session, so a rerun finds it
        n = next(
            (
                i
                for i, t in enumerate(self.created, 1)
                if (t.repo, t.title) == (task.repo, task.title) and key in t.body
            ),
            0,
        )
        if n:
            return (f"note000{n}", f"note000{n}-0") if f"note000{n}" not in self.hidden else None
        if (task.repo, task.title) in self.twins:
            raise BackendError("conflict", f"{task.repo} already has an open part titled {task.title!r}")
        return None

    def add(self, task: NewTask) -> str:
        if self.fail_at == len(self.created):
            raise self.fail
        self.created.append(task)
        return f"note000{len(self.created)}"

    def card_of(self, note8: str, task: NewTask) -> str | None:
        if note8 in self.broken:
            raise BackendError("upstream_unavailable", "todo MCP is down")
        return None if note8 in self.hidden else f"{note8}-0"

    def start(self, card: str) -> str:
        self.started.append(card)
        return self.outcome


@pytest.fixture
def board() -> FakeBoard:
    return FakeBoard()


@pytest.fixture
def git(sysroot: Path, monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    """Six untagged sessions in a clone of kuhyx/demo, one in $HOME, and the git answer for the clone."""
    root = sysroot / "home/tester/src"
    for name in ("demo", "other"):
        (root / name / ".git").mkdir(parents=True)
    monkeypatch.setenv("TODOIMPL_SRC", str(root))
    monkeypatch.setattr(movable, "now", lambda: 1792656002.0 + 7200)
    monkeypatch.setattr(mark, "now", lambda: 1792600000.0)
    for n, sid in enumerate(SIDS):
        prompt = f"do thing {n}\n## not a heading\ndone_check: false\n```"
        fx.write(
            fx.projects_dir(sysroot), [*fx.session(f"halfway {n}", prompt), fx.ai_title(f"Task {n}")], sid=sid
        )
    home = [fx.user("tidy ~"), fx.assistant("hm", cwd=HOME_CWD)]
    home[0]["cwd"] = HOME_CWD
    fx.write(fx.projects_dir(sysroot), home, sid=fx.OTHER_SID, project_dir="-home-tester")
    argv = ("git", "-C", str(sysroot / fx.CWD.lstrip("/")), "remote", "get-url", "origin")
    return FakeRunner({argv: ok(argv, "https://github.com/kuhyx/demo.git\n")})


def marks() -> dict[str, object]:
    path = api.marks_path()
    return json.loads(path.read_text("utf-8")) if path.exists() else {}
