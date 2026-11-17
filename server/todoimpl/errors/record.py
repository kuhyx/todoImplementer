"""One app error as the contract `app-error.schema.json` `record` says it."""

from __future__ import annotations

import re
from dataclasses import dataclass

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
WORD = re.compile(r"^\S+$")


@dataclass(frozen=True)
class AppError:
    """One identical error or slow wait; the loop makes one ticket per `key`."""

    app: str
    repo: str
    signature: str
    kind: str
    message: str
    count: int
    first_seen: str
    last_seen: str
    build: int
    top_frame: str | None = None
    version_name: str | None = None
    detail: str | None = None
    open: bool = True

    @property
    def key(self) -> str:
        """`<app>:<signature>`: the id of the ticket, in its text and in the ledger."""
        return f"{self.app}:{self.signature}"


def _int(value: object, floor: int) -> int | None:
    """Return the int (a bool is not one here) at or above `floor`, else None."""
    if isinstance(value, bool) or not isinstance(value, int) or value < floor:
        return None
    return value


def _text(raw: dict[str, object], name: str, *, empty: bool = False) -> str | None:
    """Return a string field, None when it is missing, not a string or (unless `empty`) blank."""
    value = raw.get(name)
    return value if isinstance(value, str) and (empty or value != "") else None


def parse(raw: object) -> AppError | None:
    """Return the record, or None when it breaks the contract (the loop skips what it cannot trust)."""
    if not isinstance(raw, dict):
        return None
    app, repo, sig, kind = (_text(raw, name) for name in ("app", "repo", "signature", "kind"))
    first, last, message = (
        _text(raw, "first_seen"),
        _text(raw, "last_seen"),
        _text(raw, "message", empty=True),
    )
    count, build, opens = _int(raw.get("count"), 1), _int(raw.get("build"), 0), raw.get("open", True)
    if app is None or repo is None or sig is None or kind is None or first is None or last is None:
        return None
    if message is None or count is None or build is None or not isinstance(opens, bool):
        return None
    if not (NAME.match(app) and REPO.match(repo) and WORD.match(sig)):
        return None
    top, version, detail = (raw.get(name) for name in ("top_frame", "version_name", "detail"))
    if not all(value is None or isinstance(value, str) for value in (top, version, detail)):
        return None
    top, version, detail = (value if isinstance(value, str) else None for value in (top, version, detail))
    return AppError(app, repo, sig, kind, message, count, first, last, build, top, version, detail, opens)
