"""Tell a credits failure (no balance, key not allowed to spend) from an ordinary failed turn."""

from __future__ import annotations

import re

# Never retried: "API Error" would otherwise read as transient (retry.TRANSIENT) and loop.
EXHAUSTED = re.compile(
    r"credit balance is too low|insufficient (?:credit|fund|balance)|out of (?:api )?credits"
    r"|billing_error|plans? (?:&|and) billing|invalid x-api-key|authentication_error|permission_error"
    r"|organization (?:has been )?disabled|(?:spend|usage|credit) limit",
    re.IGNORECASE,
)


def exhausted(text: str) -> bool:
    """Return True when a credit turn's final text says the credits ran out or the key may not pay."""
    return EXHAUSTED.search(text) is not None
