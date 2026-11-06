"""Learned allow rules in `$TODOIMPL_HOME/allow.json` (global, per repo, per task) for --allowedTools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .files import read_json, write_json

if TYPE_CHECKING:
    from pathlib import Path

SCOPES = {"global": None, "repo": "repos", "task": "tasks"}


def _load(root: Path) -> dict[str, object]:
    data = read_json(root / "allow.json")
    return data if isinstance(data, dict) else {}


def _bucket(data: dict[str, object], scope: str, key: str) -> list[str]:
    group = SCOPES[scope]
    holder = data if group is None else data.get(group)
    if not isinstance(holder, dict):
        return []
    found = holder.get(key if group else "global")
    return [r for r in found if isinstance(r, str)] if isinstance(found, list) else []


def rules_for(root: Path, repo: str | None, task_id: str) -> tuple[str, ...]:
    """Every rule that applies to this task: global, its repo's, its own."""
    data = _load(root)
    both = _bucket(data, "global", "") + _bucket(data, "repo", repo or "") + _bucket(data, "task", task_id)
    return tuple(dict.fromkeys(both))


def add(root: Path, scope: str, key: str, rules: tuple[str, ...]) -> list[str]:
    """Learn rules in a scope; return the ones that were new."""
    data = _load(root)
    have = _bucket(data, scope, key)
    new = [r for r in dict.fromkeys(rules) if r not in have]
    if new:
        group = SCOPES[scope]
        if group is None:
            data["global"] = have + new
        else:
            holder = data.get(group)
            table = holder if isinstance(holder, dict) else {}
            table[key] = have + new
            data[group] = table
        write_json(root / "allow.json", data)
    return new
