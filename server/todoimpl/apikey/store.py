"""Where the Claude Console API key lives and how it is read and written (never printed, never logged)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

KEY_PATTERN = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{20,}"
)  # prefixes vary (api03, usr, ...): the live check judges


@dataclass(frozen=True)
class Meta:
    """`anthropic_api_key.json`: when kuhy created the key and when the Console expires it."""

    created: date
    expires: date


def key_path() -> Path:
    """`$TODOIMPL_APIKEY`, else ~/.config/todoImplementer/anthropic_api_key."""
    given = os.environ.get("TODOIMPL_APIKEY")
    return Path(given) if given else Path.home() / ".config" / "todoImplementer" / "anthropic_api_key"


def meta_path() -> Path:
    """Return the metadata path, beside the key: `<key path>.json`."""
    key = key_path()
    return key.with_name(key.name + ".json")


def is_key(text: str) -> bool:
    """Return True when text is exactly one Anthropic API key (no whitespace around it)."""
    return KEY_PATTERN.fullmatch(text) is not None


def read_raw() -> str | None:
    """Return the stripped key file text, None when the file is missing, unreadable or blank."""
    try:
        text = key_path().read_text(encoding="utf-8").strip()
    except OSError, UnicodeDecodeError:
        return None
    return text or None


def read_key() -> str | None:
    """Return the stored key, None when missing, empty or not shaped like a key."""
    raw = read_raw()
    return raw if raw is not None and is_key(raw) else None


def read_meta() -> Meta | None:
    """Return the stored dates, None when the file is missing or not `{"created": ISO, "expires": ISO}`."""
    try:
        data = json.loads(meta_path().read_text(encoding="utf-8"))
        return Meta(date.fromisoformat(data["created"]), date.fromisoformat(data["expires"]))
    except OSError, ValueError, KeyError, TypeError:
        return None


def _write(path: Path, text: str) -> Path:
    """Write text to a fresh 0600 temp file beside path and return it (mkstemp creates 0600)."""
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    return Path(name)


def save(key: str, created: date, expires: date) -> None:
    """Store key and its dates, both files mode 0600, each replaced atomically.

    A non-key raises ValueError before anything is touched, so a stored key is never clobbered by junk.
    """
    if not is_key(key):
        msg = "not an Anthropic API key"
        raise ValueError(msg)
    target = key_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = json.dumps({"created": created.isoformat(), "expires": expires.isoformat()}) + "\n"
    staged = [(_write(target, key + "\n"), target), (_write(target, meta), meta_path())]
    try:
        for temp, final in staged:
            temp.replace(final)
    finally:
        for temp, _ in staged:
            with contextlib.suppress(FileNotFoundError):
                temp.unlink()
