"""The one rule for a note without a repo: it is kuhy's (Yours) unless triage found work Claude can start."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.triage.label import STARTABLE
from todoimpl.umbrella.note import is_umbrella

if TYPE_CHECKING:
    from .types import TaskLike


def is_yours(task: TaskLike) -> bool:
    """Say whether the card is a repo-less note nothing can start (no umbrella, no startable label).

    The label (`CardTask.triage`, read from `triage.json` by the board fetch) is `new_repo` or `research` for
    work that has a pipeline of its own; `manual` and an untriaged note stay Yours (DOCS-triage.md).
    """
    return task.repo is None and not is_umbrella(task.body) and getattr(task, "triage", None) not in STARTABLE
