"""A red or cut no-limit step becomes a ticket through the errors loop (DOCS-errors.md), one per failure.

Red: the step's failing tests (pytest `FAILED <id>`, vitest `FAIL <file>`) are one record each; a red step
that names none is one record of its own. Records live in `<error state>/app-errors/nolimit.json`, a contract
report keyed by repo and signature, so the same failure seen again counts up instead of filing twice.
Cut at 60 s: `stall.slowstep.file`, the same `slow-<step>` ticket a stalled card's gate step files.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.errors.sources import state_base
from todoimpl.runner import heavybuild
from todoimpl.runner.files import read_json
from todoimpl.stall import slowstep

if TYPE_CHECKING:
    from pathlib import Path

    from .repos import Repo
    from .steps import Step

FILE = "nolimit.json"
KIND = "nolimit.red"
PREFIX = "nolimit-"
MESSAGE = "the no-limit runner found {what} red ({step}): make it green"
GAP = "the no-limit runner found {file} not fully covered (lines {lines}, {branches} branches): cover it"
DETAIL = 1500
FAILED = (
    re.compile(r"^FAILED (\S+)", re.MULTILINE),  # pytest's short summary
    re.compile(r"^\s*FAIL\s+(\S+)", re.MULTILINE),  # vitest's file line
)


def path() -> Path:
    """Return the runner's report: a `*.json` under app-errors is a source of the errors loop."""
    return state_base() / "app-errors" / FILE


def failures(step: Step) -> list[str]:
    """Return the failing test ids the step's output names, in order, each once."""
    found = [hit for pattern in FAILED for hit in pattern.findall(step.tail)]
    return list(dict.fromkeys(found))


def signature(step: Step, failure: str | None) -> str:
    """Return `nolimit-<step>[-<sha8 of the test id>]`: stable for the same failure."""
    if failure is None:
        return f"{PREFIX}{step.name}"
    return f"{PREFIX}{step.name}-{hashlib.sha1(failure.encode(), usedforsecurity=False).hexdigest()[:8]}"


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat(timespec="seconds")


def _app(repo: Repo) -> str:
    return heavybuild.NOT_APP.sub("-", repo.name.lower()).strip("-") or "repo"


def _load() -> list[dict[str, Any]]:
    data = read_json(path())
    return data.get("errors", []) if isinstance(data, dict) else []


def _save(errors: list[dict[str, Any]]) -> None:
    path().parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(path(), json.dumps({"version": 1, "errors": errors}, indent=2) + "\n")


def _count(errors: list[dict[str, Any]], repo: Repo, sig: str, said: tuple[str, str], now: float) -> None:
    """Count one sighting of `sig` (message, detail) in `errors`: a new record first, the count up after."""
    text, detail = said
    app = _app(repo)
    record = next((e for e in errors if e.get("app") == app and e.get("signature") == sig), None)
    if record is None:
        record = {"app": app, "repo": repo.slug, "signature": sig, "kind": KIND, "count": 0, "build": 0,
                  "message": text, "first_seen": _iso(now)}  # fmt: skip
        errors.append(record)
    record.update(count=int(record["count"]) + 1, last_seen=_iso(now), detail=detail, open=True)


def red(repo: Repo, step: Step, now: float) -> list[str]:
    """Count one sighting of each failure of a red step; return the signatures it filed."""
    errors, filed = _load(), []
    found: list[str | None] = [*failures(step)] or [None]
    for failure in found:
        sig = signature(step, failure)
        text = MESSAGE.format(what=failure or f"`{step.command}`", step=step.name)
        detail = f"exit {step.exit_code} after {step.seconds:g} s: {step.command}\n{step.tail[-DETAIL:]}"
        _count(errors, repo, sig, (text, detail), now)
        filed.append(sig)
    _save(errors)
    return filed


def gap(repo: Repo, found: dict[str, Any], now: float) -> str:
    """Count one sighting of an uncovered file (a `coverage-gaps --json` entry); return its signature."""
    file = str(found["path"])
    sig = f"{PREFIX}coverage-{hashlib.sha1(file.encode(), usedforsecurity=False).hexdigest()[:8]}"
    lines = found.get("missed_lines") or "-"
    text = GAP.format(file=file, lines=lines, branches=found.get("missed_branch_count", 0))
    errors = _load()
    _count(errors, repo, sig, (text, json.dumps(found)[:DETAIL]), now)
    _save(errors)
    return sig


def resolve(repo: Repo) -> int:
    """Mark the repo's open records resolved (its gate is green); return how many were open."""
    errors = _load()
    mine = [e for e in errors if e.get("app") == _app(repo) and e.get("open") is not False]
    for record in mine:
        record["open"] = False
    if mine:
        _save(errors)
    return len(mine)


def slow(repo: Repo, step: Step, now: float) -> str:
    """File the cut step as `slow-nolimit-<step>` of the repo; return the signature."""
    name = f"{PREFIX}{step.name}"
    slowstep.file(repo.slug, name, f"no-limit step cut at 60 s: {step.command}", now)
    return f"{slowstep.PREFIX}{name}"
