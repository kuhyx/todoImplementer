"""Auto retry of a turn that died for a reason kuhy cannot fix: offline, API 5xx, overloaded, or a crash."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

PAUSED = "paused_retry"
DEFAULT_BACKOFF = (60.0, 300.0, 1800.0)
DEFAULT_LONG_WAIT = 3600.0
BACKOFF = DEFAULT_BACKOFF
LONG_WAIT = DEFAULT_LONG_WAIT
MAX_CRASH_RETRIES = 3
TAIL = 300
TAIL_READ = 600
SHOWN = 120
NO_RESULT = "claude exited without a result"
TRANSIENT = re.compile(
    r"ENOTFOUND|EAI_AGAIN|ECONNRESET|ECONNREFUSED|ECONNABORTED|ETIMEDOUT|ENETUNREACH|EHOSTUNREACH|EPIPE"
    r"|getaddrinfo"
    r"|network"
    r"|offline"
    r"|socket hang up"
    r"|fetch failed"
    r"|timed out"
    r"|overloaded"
    r"|API Error"
    r"|unable to connect"
    r"|connection (?:error|reset|refused|closed|lost)"
    r"|cannot reach MCP"
    r"|(?:status|http|error|code)\D{0,12}\b5\d\d\b",
    re.IGNORECASE,
)


class RetryLaterError(Exception):
    """The turn failed in a way that may pass; args are (run the stage again at this epoch, why)."""


def is_transient(text: str) -> bool:
    """Return True when the failure text reads like network, DNS, 5xx or overload."""
    return TRANSIENT.search(text) is not None


def delay(attempt: int) -> float:
    """Seconds before retry number `attempt` (0-based): 1 min, 5 min, 30 min, then hourly forever."""
    return BACKOFF[attempt] if attempt < len(BACKOFF) else LONG_WAIT


def stderr_tail(run_dir: Path, role: str) -> str:
    """Return the end of the newest `<role>-<ts>.stderr.log` of this run (empty when there is none)."""
    logs = sorted(run_dir.glob(f"{role}-*.stderr.log"))
    if not logs:
        return ""
    return logs[-1].read_text(encoding="utf-8", errors="replace").strip()[-TAIL_READ:]


def failure(
    st: RunState, *, now: float, stage: str, reason: str, tail: str
) -> RetryLaterError | NeedsYouError:
    """Count the failure and return what to raise: a timed retry, or Needs you once crashes hit the cap."""
    if not is_transient(f"{tail}\n{reason}"):
        crashes = int(st.extra.get("crash_retries", 0))
        if crashes >= MAX_CRASH_RETRIES:
            detail = tail.strip()[-TAIL:]
            msg = f"The {stage} turn failed: {reason}" + (f" (stderr: {detail})" if detail else "")
            return NeedsYouError(msg, "run_failed")
        st.extra["crash_retries"] = crashes + 1
    lines = tail.strip().splitlines()
    return later(st, now, lines[-1] if reason == NO_RESULT and lines else reason)


def later(st: RunState, now: float, reason: str) -> RetryLaterError:
    """Count one more attempt and return the retry that waits the next backoff step."""
    attempts = int(st.extra.get("retries", 0))
    st.extra["retries"] = attempts + 1
    return RetryLaterError(now + delay(attempts), reason[:SHOWN])


def pause(st: RunState, until: float, reason: str) -> None:
    """Rest the run in paused_retry; state.json keeps the stage to rerun and when (the caller saves)."""
    if st.stage not in (PAUSED, "paused_limit"):
        st.extra["resume_stage"] = st.stage
    st.extra["retry_reason"] = reason
    st.resume_at = until
    st.stage = PAUSED
