"""Parse the fenced `ask` block of a note or reply; a malformed block yields nothing (free-text fallback)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .risk import effective_risk

FENCE = re.compile(r"^```ask[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
LINE = re.compile(r"^(choice|command|screenshot)[ \t]+([a-z][a-z0-9_]{0,15}):[ \t]*(.+)$")
MAX_OPTIONS = 8
SHOT = re.compile(r"(?:(?!\.{1,2}/)[\w.-]+/)*[\w.-]+\.png", re.ASCII)


@dataclass(frozen=True)
class Ask:
    """One ask: a choice with fixed options, an exact command to run, or a screenshot to approve."""

    id: str
    type: str
    title: str
    options: tuple[str, ...] = ()
    recommended: str | None = None
    command: str | None = None
    shot: str | None = None
    risk: str = "risky"


def _fields(rest: str) -> tuple[list[str], str | None]:
    """Split `a | b | risk=reversible` into the fields and the risk tag."""
    parts = [p.strip() for p in rest.split(" | ")]
    tag = None
    if parts and parts[-1].startswith("risk="):
        tag = parts.pop()[5:].strip()
    return parts, tag


def _one(kind: str, ident: str, rest: str) -> Ask | None:
    parts, tag = _fields(rest)
    if not parts or not parts[0] or tag not in (None, "reversible", "risky"):
        return None
    title = parts[0]
    if kind == "command":
        return Ask(ident, kind, title, command=title, risk=effective_risk(tag, title))
    if kind == "screenshot":
        shot = parts[1] if len(parts) == 2 else None  # noqa: PLR2004
        if len(parts) > 2 or (shot is not None and not SHOT.fullmatch(shot)):  # noqa: PLR2004
            return None
        return Ask(ident, kind, title, shot=shot, risk=effective_risk(tag, title))
    options = [o.removeprefix("*").strip() for o in parts[1:]]
    stars = [o for o in parts[1:] if o.startswith("*")]
    if not 2 <= len(options) <= MAX_OPTIONS or len(stars) != 1 or not all(options):  # noqa: PLR2004
        return None
    rec = stars[0].removeprefix("*").strip()
    return Ask(ident, kind, title, tuple(options), rec, risk=effective_risk(tag, title, *options))


def parse_asks(text: str) -> list[Ask]:
    """Return the asks of the last `ask` fence in text; [] when there is none or any line is malformed."""
    blocks = FENCE.findall(text or "")
    if not blocks:
        return []
    out: list[Ask] = []
    for raw in blocks[-1].splitlines():
        if not raw.strip():
            continue
        found = LINE.match(raw.strip())
        ask = _one(*found.groups()) if found else None
        if ask is None or any(a.id == ask.id for a in out):
            return []
        out.append(ask)
    return out
