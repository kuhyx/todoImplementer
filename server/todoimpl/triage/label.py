"""The label of a repo-less note and its file `<run dir>/triage.json` (DOCS-triage.md).

The file survives restarts and is keyed by a digest of title and body, so an edited note is triaged again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "triage.json"
NEW_REPO, EXISTING_REPO, ALL_REPOS, RESEARCH, MANUAL = (
    "new_repo",
    "existing_repo",
    "all_repos",
    "research",
    "manual",
)
LABELS = (NEW_REPO, EXISTING_REPO, ALL_REPOS, RESEARCH, MANUAL)
STARTABLE = (
    NEW_REPO,
    RESEARCH,
)  # a repo-less card with one of these labels offers Start; the rest wait or are Yours


@dataclass(frozen=True)
class Verdict:
    """What the classifier decided: the label plus the one field the label needs."""

    label: str
    reason: str = ""
    repo: str | None = None  # existing_repo: owner/name
    name: str | None = None  # new_repo: the kebab-case name to create
    token: str | None = None  # all_repos: a literal the change touches (`git grep -F`), None = every repo
    path: str | None = None  # all_repos: the directory to look in (`.github`), None = the whole repo


def digest(title: str, body: str) -> str:
    """Return 16 hex chars of the note text: a changed note has another digest."""
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()[:16]


def load(directory: Path) -> dict[str, Any] | None:
    """Return the stored record, None when the file is missing or damaged."""
    try:
        data = json.loads((directory / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) and data.get("label") in LABELS else None


def save(directory: Path, verdict: Verdict, text_digest: str, at: float, **extra: object) -> None:
    """Write the record durably; `extra` holds what the acting step learned (error, applied, new card)."""
    record = {**asdict(verdict), "digest": text_digest, "at": at, **extra}
    atomic.write_text(directory / FILE, json.dumps(record, ensure_ascii=False, indent=1))


def update(directory: Path, **extra: object) -> None:
    """Add facts to the stored record (the repo made for a `new_repo` note, the card it became)."""
    found = load(directory)
    if found is not None:
        atomic.write_text(directory / FILE, json.dumps({**found, **extra}, ensure_ascii=False, indent=1))


def label_of(directory: Path) -> str | None:
    """Return the stored label, None while the note is untriaged."""
    found = load(directory)
    return None if found is None else str(found["label"])
