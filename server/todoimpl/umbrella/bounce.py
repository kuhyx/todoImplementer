"""An umbrella child answers to no one: `Q:`/`A:` and red checks go back to work before kuhy is paged.

A child's live check or implement turn that ends on `A:` (text left in a file, a pin to bump, a tool that
needs reconnecting) used to rest on kuhy at once (T1952). Now the child gets `MAX_BOUNCES` more passes with
the reply as its fix brief; only then does it rest, and the umbrella's card says what it waits for (T1953).
Red checks get `MAX_CHILD_CHECK_FIXES` fix turns, the old red included (T1954). A child whose checks did not
pass never ships (T1955).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.runner.deploy import PREFIX

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

MAX_BOUNCES = 3
MAX_CHILD_CHECK_FIXES = 5
SHORT = 100
LISTED = 5  # children named per kind on the umbrella's card
UNATTENDED = (
    "(runner) You are an unattended umbrella child: nobody answers `Q:` or `A:`. Do the work yourself "
    "(edit, bump pins, run the tool, reconnect what you need) and end with `D:`. Use `A:` only for a step "
    "that truly needs kuhy's hands."
)
OWN_RED = (
    "(runner) You own every red check, also one that was red before you started (dependency-freshness: bump "
    "the pins to the newest stable; format; fix the tests). Do not report it as someone else's."
)
_TAGGED = re.compile(r"^\s*[QA]:\s*(.*)$")


def is_child(st: RunState) -> bool:
    """Return True for a run that is a child of an umbrella."""
    return "umbrella_round" in st.extra


def again(st: RunState) -> bool:
    """Count one more pass for a child that ended on `Q:`/`A:`; False when it is no child or out of passes."""
    passes = int(st.extra.get("bounces", 0))
    if not is_child(st) or passes >= MAX_BOUNCES:
        return False
    st.extra["bounces"] = passes + 1
    return True


def brief(reply: str) -> str:
    """Return the fix brief for a bounced reply: the unattended rule, then what the child said."""
    return f"{UNATTENDED}\n\n{reply.strip()}"


def check_cap(st: RunState, normal: int) -> int:
    """Return how many fix turns red checks get: a child gets more than a single run."""
    return max(normal, MAX_CHILD_CHECK_FIXES) if is_child(st) else normal


def red_tail(st: RunState, tail: str) -> str:
    """Return the failure tail of red checks; a child's starts with the rule that old red is its own."""
    return f"{OWN_RED}\n\n{tail}" if is_child(st) else tail


def unverified(st: RunState | None) -> bool:
    """Return True for a child whose checks did not pass (or never ran)."""
    return st is not None and is_child(st) and (st.checks or {}).get("passed") is not True


def short(text: str) -> str:
    """Collapse whitespace and cut to `SHORT` characters."""
    flat = " ".join(text.split())
    return flat if len(flat) <= SHORT else flat[: SHORT - 1].rstrip() + "…"


def undeployed(st: RunState | None) -> bool:
    """Return True for a child whose code is on origin but whose deploy is missing or failed (T1967)."""
    return st is not None and (st.error or "").startswith(PREFIX)


def needs(st: RunState | None, symptom: str = "") -> str:
    """Return what a child waits for, shortened: its `Q:`/`A:` line, else its error, else the last issue."""
    if st is None:
        return short(symptom)
    if st.last_tag in ("Q", "A"):
        lines = str(st.extra.get("last_reply", "")).splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if found := _TAGGED.match(lines[i]):
                return short(" ".join([found.group(1), *lines[i + 1 :]]))
    return short((st.error or symptom).removeprefix(f"{PREFIX}: "))


def _listed(pairs: list[tuple[str, str]]) -> str:
    """List the first `LISTED` children, each with what it waits for (its own repo name left out of that)."""
    return "; ".join(
        f"{repo} ({why.removeprefix(f'{repo} ')})" if why else repo for repo, why in pairs[:LISTED]
    )


def summary(total: int, need: list[tuple[str, str]], held: list[tuple[str, str]]) -> str:
    """Say which children need kuhy and which are pushed, not deployed (each a repo and what it waits for)."""
    parts = [f"{len(need)} of {total} children need you: {_listed(need)}"] if need else []
    if held:
        lead = (
            f"{len(held)} pushed, not deployed"
            if need
            else f"{len(held)} of {total} children pushed, not deployed"
        )
        parts.append(f"{lead}: {_listed(held)}")
    return ". ".join(parts)
