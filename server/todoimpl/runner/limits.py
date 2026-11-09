"""Plan limits: rate_limit_event parsing and the shared `<root>/limit-until` file."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.usage.limits import UNTIL_FILE, limit_state

if TYPE_CHECKING:
    from pathlib import Path

FALLBACK_PAUSE = 1800.0
LIMIT_TEXT = re.compile(r"usage limit|hit your (?:usage )?limit|limit reached", re.IGNORECASE)
EPOCH_IN_TEXT = re.compile(r"\|(\d{10})\b")


@dataclass(frozen=True)
class LimitInfo:
    """Top-level fields of one rate_limit_event."""

    status: str
    resets_at: float | None
    kind: str | None
    overage_status: str | None
    using_overage: bool = False


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def parse_event(obj: dict[str, Any]) -> LimitInfo | None:  # noqa: D103
    info = obj.get("rate_limit_info")
    if not isinstance(info, dict):
        return None
    resets = info.get("resetsAt")
    return LimitInfo(
        status=_opt_str(info.get("status")) or "",
        resets_at=float(resets) if isinstance(resets, int | float) and not isinstance(resets, bool) else None,
        kind=_opt_str(info.get("rateLimitType")),
        overage_status=_opt_str(info.get("overageStatus")),
        using_overage=info.get("isUsingOverage") is True,
    )


def blocking(info: LimitInfo | None) -> bool:
    """Only the top-level status counts: `allowed_warning` events also carry overageStatus=rejected."""
    return info is not None and info.status == "rejected" and not info.using_overage


def pause_until(info: LimitInfo | None, text: str, *, is_error: bool, now: float) -> float | None:
    """When to resume after this turn; None when it hit no limit. Unknown reset time: retry in 30 min."""
    if info is not None and blocking(info):
        return info.resets_at or now + FALLBACK_PAUSE
    if not is_error or not LIMIT_TEXT.search(text):
        return None
    found = EPOCH_IN_TEXT.search(text)
    return float(found.group(1)) if found else now + FALLBACK_PAUSE


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_until(root: Path, until: float) -> None:  # noqa: D103
    _write(root / UNTIL_FILE, f"{until}\n")


def active_until(root: Path, now: float) -> float | None:  # noqa: D103
    state = limit_state(root)
    return state.until if state.active(now) else None


def clear(root: Path) -> None:  # noqa: D103
    (root / UNTIL_FILE).unlink(missing_ok=True)
