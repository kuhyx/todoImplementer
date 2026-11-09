"""kuhy's one global setting: fall back to free API credits (default on), in ~/.config/todoImplementer/."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def enabled() -> bool:
    """Return the fallback setting; a missing, unreadable or non-boolean value means the default, on."""
    value = _read().get(KEY)
    return value if isinstance(value, bool) else True


def set_enabled(*, value: bool) -> None:
    """Store the setting atomically, keeping any other key of the file."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps({**_read(), KEY: value}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
