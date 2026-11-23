"""A card being created after Start (T2529): its repo is made or its note triaged, so it is no Backlog card.

The triage service holds such cards in memory until the job hands over to a run (`triage/service.py`). The
card shows Working with one disabled Start; Cancel and Done manually would race the job, so none are offered.
"""

from __future__ import annotations

from typing import Any

from .button import Action
from .status import Column, Status

CREATING = "being created"  # kuhy's own words for it (the refusal of a second Start says the same)


def overlay(card: dict[str, Any]) -> None:
    """Turn a card being created (first Start, or Retry of a failed creation) into Working, Start disabled."""
    card.update(
        status=Status.WORKING.value,
        column=Column.RUNNING.value,
        current=CREATING,
        needs=None,  # a Retry of a failed creation: the failure is no longer what the card waits on
        actions=[Action("start", "Start", enabled=False, reason=CREATING).to_dict()],
    )
