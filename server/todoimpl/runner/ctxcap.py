"""Context cap: a board session never grows past `ctx_cap_tokens` tokens or `call_cap` calls (DOCS-turns.md).

The stream of both routes (plan CLI and credit SDK) carries each assistant message's usage. Its main-thread
context is input + cache creation + cache read tokens; a subagent's message (`parent_tool_use_id` set) is
another context and is ignored. A call is one main-thread assistant message (`Meter`). At or above either cap
the turn is stopped once no tool call is in flight (after the current tool result, never mid-call) and the
role's next turn starts a fresh session seeded from the server-built handoff summary. A cap stop is neither a
crash nor a kill: it touches no retry counter, adds no backoff and never rests the card on kuhy.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from todoimpl.credits import setting

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState

    from .stream import StreamParser, TurnResult

log = logging.getLogger("todoimpl.runner")
ENV = "TODOIMPL_CTX_CAP"  # beats the settings file (tests, one-off runs)
CALL_ENV = "TODOIMPL_CALL_CAP"
CAP_KEY = "ctx_cap_tokens"  # ~/.config/todoImplementer/settings.json (`credits.setting`), 0 = off
CALL_KEY = "call_cap"
DEFAULT_CAP = 150_000  # kuhy, 2026-11-28: cache reads were 3/4 of the cost of sessions of 740k tokens
DEFAULT_CALL_CAP = 150
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
CALL_SEED = (
    "(runner) The previous session was stopped at the call cap ({calls} of {call_cap} calls). "
    "Uncommitted work may sit in the worktree: check `git status` and `git log` first, then carry on."
)


def _limit(env: str, key: str, default: int) -> int:
    """Return `$env`, else the settings file's `key`; 0 = off, junk or a negative value is the default."""
    given = os.environ.get(env)
    if given:
        try:
            value = int(given)
        except ValueError:
            return default
        return value if value >= 0 else default
    stored = setting.read().get(key)
    return stored if isinstance(stored, int) and not isinstance(stored, bool) and stored >= 0 else default


def cap() -> int:
    """Return the cap in tokens (`$TODOIMPL_CTX_CAP`, else settings `ctx_cap_tokens`); 0 = off."""
    return _limit(ENV, CAP_KEY, DEFAULT_CAP)


def call_cap() -> int:
    """Return the cap in calls per session (`$TODOIMPL_CALL_CAP`, else settings `call_cap`); 0 = off."""
    return _limit(CALL_ENV, CALL_KEY, DEFAULT_CALL_CAP)


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


class Meter:
    """Counts a stream's main-thread calls (one per assistant message id) and the tool calls in flight."""

    def __init__(self) -> None:  # noqa: D107
        self.calls = 0
        self.pending: set[str] = set()
        self._seen: set[object] = set()

    def assistant(self, event: dict[str, Any]) -> int | None:
        """Take a main-thread assistant event; return its context (None: not metered)."""
        tokens = context_of(event)
        if tokens is None:
            return None
        message = event["message"]
        mid = message.get("id")
        if mid is None or mid not in self._seen:  # one message streams as several events (thinking, tool_use)
            self._seen.add(mid)
            self.calls += 1
        content = message.get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                self.pending.add(str(block.get("id")))
        return tokens

    def answered(self, event: dict[str, Any]) -> bool:
        """Take a user event; True when it answered main-thread tool calls and none is in flight any more."""
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("parent_tool_use_id") is not None or not isinstance(content, list):
            return False
        blocks = (b for b in content if isinstance(b, dict) and b.get("type") == "tool_result")
        ids = {str(b.get("tool_use_id")) for b in blocks}
        self.pending -= ids
        return bool(ids) and not self.pending


def session_calls(st: RunState, role: str, parser: StreamParser) -> int:
    """Return the calls of the role's session so far: its earlier turns (same session id) plus this stream."""
    prior = st.sessions.get(role) or {}
    same = prior.get("session_id") == parser.result.session_id
    return (int(prior.get("calls", 0)) if same else 0) + parser.meter.calls


def size(res: TurnResult, prior: dict[str, Any] | None = None) -> dict[str, int]:
    """Return the `sessions[role]` fields: the last main-thread context and the calls.

    `prior` is the role's entry before this turn; its calls carry on when this turn ran the same session.
    """
    out = {"context_tokens": res.context_tokens} if res.context_tokens else {}
    if res.calls:
        before = int(prior.get("calls", 0)) if prior and prior.get("session_id") == res.session_id else 0
        out["calls"] = before + res.calls
    return out


def _marker(st: RunState, role: str) -> dict[str, int]:
    found: dict[str, int] = st.extra.get(FRESH, {}).get(role, {})
    return found


def brake(
    st: RunState, role: str, stop: Callable[[], None], parser: StreamParser | None = None
) -> Callable[[int], None] | None:
    """Return the callback for a turn's stream parser: the first context or call count at a cap stops it.

    With a `parser` the stop waits until no tool call is in flight (`parser.on_idle` fires on the tool result
    that answers the last one); a stop never cuts a tool call. Without one it stops at once.
    """
    st.extra.pop(HIT, None)  # a stop of an earlier turn that nobody took is no news
    limit, call_limit = cap(), call_cap()
    if not (limit or call_limit) or _marker(st, role).get("streak", 0) >= MAX_STREAK:
        return None
    stopped = False

    def settle() -> None:
        nonlocal stopped
        if HIT in st.extra and not stopped and (parser is None or not parser.meter.pending):
            stopped = True
            stop()

    def on_context(tokens: int) -> None:
        if HIT not in st.extra:
            calls = session_calls(st, role, parser) if parser is not None else 0
            by_tokens = bool(limit) and tokens >= limit
            by_calls = bool(call_limit) and calls >= call_limit
            if not (by_tokens or by_calls):
                return
            hit: dict[str, Any] = {"role": role, "tokens": tokens, "cap": limit}
            if not by_tokens:
                hit |= {"calls": calls, "call_cap": call_limit}
            st.extra[HIT] = hit
            log.info(
                "context cap: the %s session of %s reached %d tokens, %d calls (caps %d, %d)",
                role, st.task_id, tokens, calls, limit, call_limit,
            )  # fmt: skip
        settle()

    if parser is not None:
        parser.on_idle = settle
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
    if not found:
        return ""
    if "call_cap" in found:
        return CALL_SEED.format(calls=found["calls"], call_cap=found["call_cap"])
    return SEED.format(tokens=found["tokens"], cap=found["cap"])


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
