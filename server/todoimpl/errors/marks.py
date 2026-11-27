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
TOKENOPT = "tokenopt"  # state.extra: set when the reset watch starts its card ({key, at}; DOCS-credits.md)
RESET_KEY = re.compile(r"^[ \t]*Reset-Key:[ \t]*(\S+)[ \t]*$", re.MULTILINE)  # its part's identity line
BOARD_APP = "todoimplementer"  # the board's own report (stalls, parse misses)
# Signatures the board files against any repo: slow gate steps, heavy builds, no-limit reds, stray edits
BOARD_SIGNATURE = re.compile(r"^(?:stall-|slow-|heavy-|nolimit-)|-stray$")


def signatures(text: str) -> list[str]:
    """Return the `app:signature` keys of the `Error-Signature:` lines in a text."""
    return SIGNATURE.findall(text)


def is_error_run(st: RunState) -> bool:
    """Say whether the errors loop started this run."""
    return KEY in st.extra


def is_tokenopt_run(st: RunState) -> bool:
    """Say whether the reset watch started this run (token optimization after a usage reset)."""
    return TOKENOPT in st.extra


def unattended(st: RunState) -> bool:
    """Say whether nobody answers this run's questions: an umbrella child, an error or a tokenopt run."""
    return "umbrella_round" in st.extra or is_error_run(st) or is_tokenopt_run(st)


def own(text: str) -> bool:
    """Say whether a part is automatic: an error ticket or a token optimization (not written by kuhy)."""
    return bool(signatures(text)) or RESET_KEY.search(text) is not None


def board_key(key: str) -> bool:
    """Say whether an errors-loop key (`<app>:<signature>`) was filed by the board, not reported by an app."""
    app, _, sig = key.partition(":")
    return app == BOARD_APP or BOARD_SIGNATURE.search(sig) is not None


def app_ticket(text: str) -> bool:
    """Say whether a part is only other apps' error reports: lowest priority, idle-only starts, Sonnet."""
    found = signatures(text)
    return bool(found) and not any(board_key(key) for key in found)


def ships_itself(st: RunState, ticked: Sequence[Part], body: str) -> bool:
    """Say whether a green error or tokenopt run ships and deploys itself: every ticked part is the board's.

    A part of kuhy's own that the session also ticked keeps the run at the gate for his Ship click. A card
    that is one plain note (no parts) counts by its own text.
    """
    if not (is_error_run(st) or is_tokenopt_run(st)):
        return False
    return all(own(part.body) for part in ticked) if ticked else own(body)
