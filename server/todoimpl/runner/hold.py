"""The one switch of the ship-by-itself rule (kuhy, 2026-11-19; DOCS-landing.md "Ship by itself").

A run that is green at the gate ships (a closing run closes) without a click. `TODOIMPL_HOLD_GATE=1` brings
the old rest at the gate back: only the test suite sets it, to drive Ship by hand. Production never does.
"""

from __future__ import annotations

import os

ENV = "TODOIMPL_HOLD_GATE"


def held() -> bool:
    """Say whether a green run rests at the gate for a click."""
    return os.environ.get(ENV) == "1"
