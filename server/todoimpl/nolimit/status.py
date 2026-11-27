"""The runner's memory, `<run root>/nolimit.json`: the cycle so far, whether it is on, and the last result.

A cycle visits every repo once, in name order, one repo per tick; a repo whose step was cut at 60 s is done
for this cycle like any other (the next cycle tries it again). The board's tracking strip shows `view()`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.runner.files import read_json

if TYPE_CHECKING:
    from pathlib import Path

    from .repos import Repo

FILE = "nolimit.json"
DEPLOYED, PUSHED, GREEN, RED, SLOW, STOPPED, READONLY = (
    "deployed", "pushed", "green", "red", "slow", "stopped", "readonly",
)  # fmt: skip
RESULTS = (DEPLOYED, PUSHED, GREEN, RED, SLOW, STOPPED, READONLY)


def load(root: Path) -> dict[str, Any]:
    """Return the saved state; anything unreadable is an empty one."""
    data = read_json(root / FILE)
    return data if isinstance(data, dict) else {}


def _save(root: Path, data: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    atomic.write_text(root / FILE, json.dumps(data, sort_keys=True) + "\n")


def pick(root: Path, repos: list[Repo]) -> Repo | None:
    """Return the next repo of the cycle; when every repo was visited a new cycle starts with the first."""
    if not repos:
        return None
    seen = {name for name in load(root).get("cycle", []) if isinstance(name, str)}
    left = [repo for repo in repos if repo.name not in seen]
    if not left:
        data = load(root)
        data["cycle"] = []
        _save(root, data)
        return repos[0]
    return left[0]


def set_active(root: Path, *, active: bool) -> None:
    """Record whether the trigger holds now (written only when it changed)."""
    data = load(root)
    if data.get("active") is not active:
        data["active"] = active
        _save(root, data)


def finish(root: Path, repo: str, result: str, now: float) -> None:
    """Record a repo's visit: it joins the cycle and becomes the last result."""
    data = load(root)
    cycle = [name for name in data.get("cycle", []) if isinstance(name, str) and name != repo]
    data.update(cycle=[*cycle, repo], last={"repo": repo, "result": result, "at": now})
    _save(root, data)


def view(root: Path) -> dict[str, Any]:
    """Return the contract's `nolimit` object (nolimit.schema.json): on or off, the last repo and result."""
    data = load(root)
    last = data.get("last")
    last = last if isinstance(last, dict) else {}
    result, at, repo = last.get("result"), last.get("at"), last.get("repo")
    ok = result in RESULTS and isinstance(at, int | float) and isinstance(repo, str)
    return {
        "active": data.get("active") is True,
        "repo": repo if ok else None,
        "result": result if ok else None,
        "at": at if ok else None,
    }
