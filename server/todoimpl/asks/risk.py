"""The fixed risk rule: a session may tag a choice `reversible`; any match here makes it risky again."""

from __future__ import annotations

import re

RISKY = re.compile(
    r"encrypt|migrat|delet|remov|\bdrop\b|push|\broot\b|sudo|pkexec|credential|password|secret|token"
    r"|api[ _-]?key"
    r"|\brm\b|wipe|format|overwrit|chattr|pacman|poweroff|reboot|force|money|pay|price|purchase|irreversib",
    re.IGNORECASE,
)


def effective_risk(tag: str | None, *texts: str) -> str:
    """Return `reversible` only for an explicit tag with no risky word anywhere in the ask; else `risky`."""
    if tag != "reversible":
        return "risky"
    return "risky" if any(RISKY.search(text) for text in texts) else "reversible"
