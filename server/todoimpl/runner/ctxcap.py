"""Context cap: a board session never grows past `$TODOIMPL_CTX_CAP` tokens (DOCS-turns.md, "Context cap").

The stream of both routes (plan CLI and credit SDK) carries each assistant message's usage. Its main-thread
context is input + cache creation + cache read tokens; a subagent's message (`parent_tool_use_id` set) is
another context and is ignored. At or above the cap the turn is stopped and the role's next turn starts a
fresh session seeded from the server-built handoff summary. A cap stop is neither a crash nor a kill: it
touches no retry counter, adds no backoff and never rests the card on kuhy.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState

    from .stream import TurnResult

log = logging.getLogger("todoimpl.runner")
ENV = "TODOIMPL_CTX_CAP"
DEFAULT_CAP = 300_000
# A role whose fresh sessions are cut again and again without one turn finishing is no longer thrashing
# for want of a smaller session: past this many cuts in a row the brake stands down for the role.
MAX_STREAK = 8
FRESH = (
    "ctx_fresh"  # {role: {tokens, cap, streak}}: the role's next turn starts fresh; ends when a turn finishes
)
HIT = "ctx_hit"  # set by the brake while a turn is read, taken by `mark` once the turn is over
RESEEDS = "ctx_reseeds"  # {role: count}: how often the cap cut that role's session
USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
SEED = (
    "(runner) The previous session was stopped at the context cap ({tokens} of {cap} tokens). "
    "Uncommitted work may sit in the worktree: check `git status` and `git log` first, then carry on."
)


def cap() -> int:
    """Return the cap in tokens: `$TODOIMPL_CTX_CAP`, `0` = off; junk or a negative value is the default."""
    try:
        value = int(os.environ.get(ENV, ""))
    except ValueError:
        return DEFAULT_CAP
    return value if value >= 0 else DEFAULT_CAP


def context_of(event: dict[str, Any]) -> int | None:
    """Return the main-thread context of an assistant event, None for any other event or a subagent's."""
    message = event.get("message")
    if event.get("parent_tool_use_id") is not None or not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    total = sum(v for k in USAGE if isinstance(v := usage.get(k), int) and not isinstance(v, bool))
    return total or None  # a synthetic message reports no usage: it says nothing about the context


def size(res: TurnResult) -> dict[str, int]:
    """Return the `sessions[role]` field for the turn's last main-thread context (none metered: nothing)."""
    return {"context_tokens": res.context_tokens} if res.context_tokens else {}


def _marker(st: RunState, role: str) -> dict[str, int]:
    found: dict[str, int] = st.extra.get(FRESH, {}).get(role, {})
    return found


def brake(st: RunState, role: str, stop: Callable[[], None]) -> Callable[[int], None] | None:
    """Return the callback for a turn's stream parser: the first context at the cap stops the turn."""
    st.extra.pop(HIT, None)  # a stop of an earlier turn that nobody took is no news
    limit = cap()
    if not limit or _marker(st, role).get("streak", 0) >= MAX_STREAK:
        return None

    def on_context(tokens: int) -> None:
        if tokens >= limit and HIT not in st.extra:
            st.extra[HIT] = {"role": role, "tokens": tokens, "cap": limit}
            log.info(
                "context cap: the %s session of %s reached %d of %d tokens", role, st.task_id, tokens, limit
            )
            stop()

    return on_context


def mark(st: RunState, role: str, res: TurnResult) -> bool:
    """Take the brake's verdict after a turn; True when the turn was cut short and its role goes on fresh."""
    hit = st.extra.pop(HIT, None)
    if hit is not None and hit.pop("role") != role:  # the stop of another role's turn that was waited for
        hit = None
    fresh: dict[str, dict[str, int]] = st.extra.setdefault(FRESH, {})
    if hit is None:
        if res.finished:  # a turn that ends well ends the streak of cuts and the fresh seed
            fresh.pop(role, None)
        if not fresh:
            st.extra.pop(FRESH)
        return False
    streak = 1 if res.finished else _marker(st, role).get("streak", 0) + 1
    fresh[role] = {**hit, "streak": streak}
    counts: dict[str, int] = st.extra.setdefault(RESEEDS, {})
    counts[role] = counts.get(role, 0) + 1
    return not res.finished


def seed(st: RunState, role: str) -> str:
    """Return the line that tells a fresh session why it is fresh, empty when its last one was not cut."""
    found = _marker(st, role)
    return SEED.format(tokens=found["tokens"], cap=found["cap"]) if found else ""


def go_on(st: RunState, res: TurnResult, *, cut: bool) -> bool:
    """Return True when a cap stopped the turn and the same stage goes on at once.

    The credit cap (`cap_hit`) goes on at the plan, resuming the session; the context cap goes on fresh.
    """
    credit = st.extra.pop("cap_hit", None)
    if cut:
        return True
    if credit and not res.finished:
        st.extra["r_continue"] = True
        return True
    return False
