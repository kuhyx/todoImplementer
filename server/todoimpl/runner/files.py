"""Run-dir layout (streams beside state.json, as todoimpl.usage globs them) and atomic JSON helpers."""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

STREAM_SUFFIX = ".stream.jsonl"
RESULT_SUFFIX = ".result.json"
EXIT_SUFFIX = ".exit.json"  # written by the turn host when claude exits: the turn is over
ROUTE_SUFFIX = ".route"  # `plan` or `credits`: which route started the turn (read again after a restart)


class NeedsYouError(Exception):
    """The run cannot go on without kuhy; `text` names exactly what is needed, `kind` is a needs_kind."""

    def __init__(self, text: str, kind: str = "run_failed") -> None:  # noqa: D107
        super().__init__(text)
        self.kind = kind
        self.text = text


def write_json(path: Path, data: object) -> None:  # noqa: D103
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> Any:  # noqa: ANN401, D103
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


def worktree_path(root: Path, run_id: str) -> Path:
    """Decide the worktree location in one place: `<root>/<item id>/wt`."""
    return root / run_id / "wt"


def new_stream(run_dir: Path, role: str, now: float) -> Path:
    """Return a fresh `<role>-<epoch>.stream.jsonl`; bump the epoch by 1 ms until the name is unused."""
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = round(now, 3)
    while (path := run_dir / f"{role}-{stamp:.3f}{STREAM_SUFFIX}").exists():
        stamp = round(stamp + 0.001, 3)
    return path


def result_path(stream: Path) -> Path:  # noqa: D103
    return stream.with_name(stream.name.removesuffix(STREAM_SUFFIX) + RESULT_SUFFIX)


def sibling(run_dir: Path, stem: str, suffix: str) -> Path:
    """Return `<run_dir>/<stem><suffix>`: the stem names every file of one turn."""
    return run_dir / f"{stem}{suffix}"


def killed_stream(run_dir: Path, role: str) -> Path | None:
    """Return the newest stream of a role without a result file: a crash or reboot killed that turn."""
    killed = [s for s in sorted(run_dir.glob(f"{role}-*{STREAM_SUFFIX}")) if not result_path(s).exists()]
    return killed[-1] if killed else None


def route_of(run_dir: Path, stem: str) -> str:
    """Return the route a turn was started on; a turn with no route file is a plan turn."""
    try:
        text = sibling(run_dir, stem, ROUTE_SUFFIX).read_text(encoding="utf-8").strip()
    except OSError:
        return "plan"
    return text if text in ("plan", "credits") else "plan"
