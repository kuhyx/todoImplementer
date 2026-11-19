"""Parse the fenced `ask` block of a note or reply; a malformed block yields nothing (free-text fallback)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .risk import effective_risk

FENCE = re.compile(r"^```ask[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
# A hyphen in an id is the commonest slip (`logo-pick`, T2134); it reads as an underscore.
LINE = re.compile(r"^(choice|command|screenshot)[ \t]+([a-z][a-z0-9_-]{0,15}):[ \t]*(.+)$")
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


def _choice(ident: str, title: str, parts: list[str], tag: str | None) -> Ask | str:
    """Return the choice of `title | opt | *rec | ...`, or why it is wrong."""
    options = [o.removeprefix("*").strip() for o in parts]
    stars = [o for o in parts if o.startswith("*")]
    if not 2 <= len(options) <= MAX_OPTIONS or not all(options):  # noqa: PLR2004
        return f"a choice has 2 to {MAX_OPTIONS} options, none empty"
    if len(stars) != 1:
        return "a choice has exactly one * option, the recommended one"
    rec = stars[0].removeprefix("*").strip()
    return Ask(ident, "choice", title, tuple(options), rec, risk=effective_risk(tag, title, *options))


def _one(kind: str, ident: str, rest: str) -> Ask | str:
    """Return the ask a line makes, or why the line is wrong."""
    parts, tag = _fields(rest)
    if not parts or not parts[0]:
        return "it has no title"
    if tag not in (None, "reversible", "risky"):
        return "risk= is reversible or risky"
    title = parts[0]
    if kind == "command":
        return Ask(ident, kind, title, command=title, risk=effective_risk(tag, title))
    if kind == "choice":
        return _choice(ident, title, parts[1:], tag)
    shot = parts[1] if len(parts) == 2 else None  # noqa: PLR2004
    if len(parts) > 2 or (shot is not None and not SHOT.fullmatch(shot)):  # noqa: PLR2004
        return "a screenshot is `screenshot <id>: <what> | shots/<name>.png`"
    return Ask(ident, kind, title, shot=shot, risk=effective_risk(tag, title))


def _scan(text: str) -> tuple[list[Ask], str | None]:
    """Return the asks of the last fence and, when a line sinks it, `<line>: <why>`."""
    blocks = FENCE.findall(text or "")
    if not blocks:
        return [], None
    out: list[Ask] = []
    for raw in blocks[-1].splitlines():
        line = raw.strip()
        if not line:
            continue
        found = LINE.match(line)
        if found is None:
            return [], f"{line[:80]}: a line starts with choice, command or screenshot, then an id"
        kind, ident, rest = found.groups()
        ask = _one(kind, ident.replace("-", "_"), rest)
        if isinstance(ask, str):
            return [], f"{line[:80]}: {ask}"
        if any(a.id == ask.id for a in out):
            return [], f"{line[:80]}: id {ask.id} is used twice"
        out.append(ask)
    return out, None


def parse_asks(text: str) -> list[Ask]:
    """Return the asks of the last `ask` fence in text; [] when there is none or any line is malformed."""
    return _scan(text)[0]


def diagnose(text: str) -> str | None:
    """Return `<line>: <why>` for the line that makes the last `ask` fence unusable, else None."""
    return _scan(text)[1]
