"""kuhy's one global setting: fall back to free API credits (default on), in ~/.config/todoImplementer/."""

from __future__ import annotations

import json
import os
from pathlib import Path

from todoimpl import atomic

KEY = "credits_fallback"
FIRST_KEY = "credits_first"


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


def enabled() -> bool:
    """Return the fallback setting; a missing, unreadable or non-boolean value means the default, on."""
    value = _read().get(KEY)
    return value if isinstance(value, bool) else True


def set_enabled(*, value: bool) -> None:
    """Store the setting atomically, keeping any other key of the file."""
    path = settings_path()
    atomic.write_text(path, json.dumps({**_read(), KEY: value}, indent=2) + "\n")


def credits_first() -> bool:
    """Return True when new turns use the free credits even with no plan limit; default off."""
    value = _read().get(FIRST_KEY)
    return value if isinstance(value, bool) else False


def set_credits_first(*, value: bool) -> None:
    """Store the credits-first setting atomically, keeping any other key of the file."""
    atomic.write_text(settings_path(), json.dumps({**_read(), FIRST_KEY: value}, indent=2) + "\n")
