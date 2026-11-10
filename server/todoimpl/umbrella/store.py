"""The umbrella run record in `state.extra["umbrella"]` and where the children's run dirs live.

Record (state.schema.json): `width` of the next round, `kids` (id, repo, title, done) in ease order, finished
`rounds` and the `current` round in progress. Only the umbrella's own drive thread writes it; the children
write their own `children/<id>/state.json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.runner.files import CHILDREN_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

RECORD = "umbrella"


def record(st: RunState) -> dict[str, Any]:
    """Return the run record, created empty on first use."""
    found: dict[str, Any] = st.extra.setdefault(
        RECORD, {"width": 1, "tier": None, "kids": [], "rounds": [], "current": None}
    )
    return found


def children_root(run_dir: Path) -> Path:
    """Return the dir holding every child's run dir."""
    return run_dir / CHILDREN_DIR


def child_dir(run_dir: Path, cid: str) -> Path:
    """Return one child's run dir (its worktree is `wt` inside)."""
    return children_root(run_dir) / cid


def taken(rec: dict[str, Any]) -> set[str]:
    """Return the ids of children a round already took (finished rounds and the one in progress)."""
    ids = {row["id"] for rnd in rec["rounds"] for row in rnd["children"]}
    current = rec.get("current")
    return ids | set(current["ids"] if current else ())
