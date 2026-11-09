"""Where the Agent SDK lives: its own venv, so the server runtime stays stdlib-only."""

from __future__ import annotations

import os
from pathlib import Path

MISSING = "Claude Agent SDK venv missing: run scripts/ensure_sdk_venv.sh"


def venv_dir() -> Path:
    """`$TODOIMPL_SDK_VENV`, else ~/.local/share/todoImplementer/sdk-venv."""
    given = os.environ.get("TODOIMPL_SDK_VENV")
    return Path(given) if given else Path.home() / ".local" / "share" / "todoImplementer" / "sdk-venv"


def python() -> Path | None:
    """Return the interpreter of credit turns (`$TODOIMPL_SDK_PYTHON` wins), None when it is missing."""
    given = os.environ.get("TODOIMPL_SDK_PYTHON")
    found = Path(given) if given else venv_dir() / "bin" / "python"
    return found if found.is_file() and os.access(found, os.X_OK) else None
