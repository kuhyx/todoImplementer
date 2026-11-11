"""Collapse raw model ids into the four groups the usage page shows.

Free (anything that is not an Anthropic ``claude-*`` id, or carries ``:free``),
Haiku, Opus, Sonnet. An Anthropic id that fits none (``claude-fable-*``) keeps
its own name. Panels filter in SQL through :func:`register`'s functions and
label their per-model rows with :func:`group_of`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

FREE = "Free"
FAMILIES = (("haiku", "Haiku"), ("opus", "Opus"), ("sonnet", "Sonnet"))
ORDER = (FREE, *(label for _, label in FAMILIES))
ANTHROPIC_PREFIX = "anthropic/"


def group_of(model: str) -> str:
    """Return a raw id's group; synthetic (``<...>``) and unmatched Claude ids stay as they are."""
    name = model.removeprefix(ANTHROPIC_PREFIX)
    if model.startswith("<") or not name:
        return model
    if name.endswith(":free") or not name.startswith("claude-"):
        return FREE
    return next((label for word, label in FAMILIES if word in name), model)


def regroup(rows: list[tuple[str, float]]) -> dict[str, float]:
    """Sum ``(model, value)`` pairs per group."""
    out: dict[str, float] = {}
    for model, value in rows:
        label = group_of(model)
        out[label] = out.get(label, 0.0) + value
    return out


def sort_key(label: str) -> tuple[int, str]:
    """Order for the dropdown: the groups first, then everything else by name."""
    return (ORDER.index(label), "") if label in ORDER else (len(ORDER), label)


def _has_group(models_json: str | None, group: str) -> bool:
    """Whether a session's ``models`` JSON object has a model of this group."""
    return any(group_of(model) == group for model in json.loads(models_json or "{}"))


def register(conn: sqlite3.Connection) -> None:
    """Add ``model_group(model)`` and ``has_model_group(models_json, group)`` to a connection."""
    conn.create_function("model_group", 1, group_of, deterministic=True)
    conn.create_function("has_model_group", 2, _has_group, deterministic=True)
