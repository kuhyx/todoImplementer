"""Helpers for the app-error tests: contract records, source files and a resolve/build shim."""

from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING, Any

from servicefakes import FakeScheduler
from todoimpl.board.state import RunState, run_dir, save

if TYPE_CHECKING:
    from pathlib import Path


def rec(**over: Any) -> dict[str, Any]:
    """One contract record (a kartka crash on build 41); keyword arguments override fields."""
    base: dict[str, Any] = {
        "app": "kartka",
        "repo": "kuhyx/kartka",
        "signature": "02b0d43d9f",
        "kind": "crash",
        "message": "SuwayomiException: x is not on the server",
        "top_frame": "SuwayomiSource._searchForUnseen (package:kartka/s.dart)",
        "count": 3,
        "first_seen": "2026-11-01T10:00:00Z",
        "last_seen": "2026-11-02T10:00:00Z",
        "build": 41,
        "version_name": "1.4.0-abc1234",
        "detail": "route /library",
    }
    return {**base, **over}


def write_report(path: Path, *records: dict[str, Any]) -> Path:
    """Write a contract report with these records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "errors": list(records)}), encoding="utf-8")
    return path


def kartka_entry(sig: str = "02b0d43d9f", **over: Any) -> dict[str, Any]:
    """One `signatures[...]` entry of kartka's state.json, shaped like the real file."""
    base: dict[str, Any] = {
        "count": 2,
        "devices": ["d1"],
        "first": "2026-11-01T10:00:00Z",
        "id": sig,
        "kinds": ["updates.check", "reader.open"],
        "last": "2026-11-02T10:00:00Z",
        "reopened": False,
        "resolved": None,
        "routes": ["/library"],
        "sample": {"at": "2026-11-02T10:00:00Z", "error": "SuwayomiException: x", "kind": "updates.check"},
        "sources": ["suwayomi:1"],
        "type": "SuwayomiException",
        "where": "SuwayomiSource._searchForUnseen (package:kartka/s.dart)",
    }
    return {**base, **over}


def write_kartka(path: Path, *entries: dict[str, Any]) -> Path:
    """Write kartka's state.json with these signature entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"seen": {}, "signatures": {e["id"]: e for e in entries}, "version": 1}
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def shim(path: Path, log: Path, *, code: int = 0, out: str = "") -> Path:
    """Write an executable that appends its argv to `log`, prints `out` and exits `code`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\necho "{out}"\nexit {code}\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class RunningScheduler(FakeScheduler):
    """Records starts like FakeScheduler and, like the real one, leaves a run in `implement` behind."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.refuse: Exception | None = None

    def start(self, id8: str, *, auto_ship: bool | None = None, extra: dict[str, Any] | None = None) -> None:
        if self.refuse is not None:
            raise self.refuse
        super().start(id8, auto_ship=auto_ship, extra=extra)
        save(run_dir(self.root, id8), RunState(task_id=id8, stage="implement", extra=dict(extra or {})))
