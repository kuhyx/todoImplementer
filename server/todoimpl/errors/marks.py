"""What marks a run, a card or a part as an app-error fix; no imports from the rest of the server."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from todoimpl.board.state import RunState
    from todoimpl.repotask.model import Part

KEY = "app_error"  # state.extra: set by the loop when it starts a card ({reason, keys, at})
PHONE = "phone_update"  # state.extra: {since, tries} while the pushed fix waits for the phone
PHONE_TRIES = "phone_tries"  # state.extra: how many times the phone wait began (survives each restart)
SIGNATURE = re.compile(r"^[ \t]*Error-Signature:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def signatures(text: str) -> list[str]:
    """Return the `app:signature` keys of the `Error-Signature:` lines in a text."""
    return SIGNATURE.findall(text)


def is_error_run(st: RunState) -> bool:
    """Say whether the errors loop started this run."""
    return KEY in st.extra


def unattended(st: RunState) -> bool:
    """Say whether nobody answers this run's questions: an umbrella child or an error run."""
    return "umbrella_round" in st.extra or is_error_run(st)


def ships_itself(st: RunState, ticked: Sequence[Part], body: str) -> bool:
    """Say whether a green error run ships and deploys by itself: every ticked part is an error part.

    A part of kuhy's own that the session also ticked keeps the run at the gate for his Ship click. A card
    that is one plain note (no parts) counts by its own text.
    """
    if not is_error_run(st):
        return False
    return all(signatures(part.body) for part in ticked) if ticked else bool(signatures(body))
