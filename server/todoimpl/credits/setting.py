"""kuhy's one global setting: fall back to free API credits (default on), in ~/.config/todoImplementer/."""

from __future__ import annotations

import json
import os
from pathlib import Path

from todoimpl import atomic

KEY = "credits_fallback"


def settings_path() -> Path:
    """`$TODOIMPL_SETTINGS`, else ~/.config/todoImplementer/settings.json."""
    given = os.environ.get("TODOIMPL_SETTINGS")
    return Path(given) if given else Path.home() / ".config" / "todoImplementer" / "settings.json"


def _read() -> dict[str, object]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def read() -> dict[str, object]:
    """Return the whole settings file; a missing, unreadable or non-object file is {}."""
    return _read()


def enabled() -> bool:
    """Return the fallback setting; a missing, unreadable or non-boolean value means the default, on."""
    value = _read().get(KEY)
    return value if isinstance(value, bool) else True


def set_enabled(*, value: bool) -> None:
    """Store the setting atomically, keeping any other key of the file."""
    path = settings_path()
    atomic.write_text(path, json.dumps({**_read(), KEY: value}, indent=2) + "\n")


MONTHLY_KEY = "credits_monthly_usd"
START_DAY_KEY = "credits_month_start_day"
MONTHLY_USD = 190.0  # the $200 grant of 2026-11-10 minus a $10 margin: billing lags, so spend overshoots
START_DAY = 10  # the grant came on the 10th; the period starts on the grant day, not the 1st
MAX_START_DAY = 28  # every month has this day


def monthly_usd() -> float:
    """Return the monthly grant to pace; a missing, non-numeric or non-positive value means the default."""
    value = _read().get(MONTHLY_KEY)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return MONTHLY_USD
    return float(value)


def start_day() -> int:
    """Return the day of the month the grant period starts (1 to 28); anything else means the default."""
    value = _read().get(START_DAY_KEY)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_START_DAY:
        return START_DAY
    return value


COST_FACTOR_KEY = "credits_cost_factor"
COST_FACTOR = 1.0  # Console billing over the ledger's SDK cost: $107.78 / $107.12 for November 2026


def cost_factor() -> float:
    """Return the factor from the ledger's SDK cost to the billed cost; a bad value means the default."""
    value = _read().get(COST_FACTOR_KEY)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return COST_FACTOR
    return float(value)


PURCHASED_KEY = "credits_purchased_usd"  # kuhy, 2026-11-27: never spend bought balance (no API reads it)


def purchased_usd() -> float:
    """Return the bought API balance kuhy wrote down (default 0); a bad value fails closed."""
    value = _read().get(PURCHASED_KEY, 0)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return 1.0
    return float(value)


MODEL_KEY = "credits_model"
MODEL = "claude-opus-5-5"  # kuhy, 2026-11-15: credit turns run on Opus 5.5 (before: sonnet, 2026-11-08)


def model() -> str:
    """Return the model credit turns run on; a missing, non-string or blank value means the default."""
    value = _read().get(MODEL_KEY)
    if not isinstance(value, str) or len(value.split()) != 1:  # one word: an id or an alias
        return MODEL
    return value.strip()
