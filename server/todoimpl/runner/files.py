"""Run-dir layout (streams beside state.json, as todoimpl.usage globs them) and atomic JSON helpers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

STREAM_SUFFIX = ".stream.jsonl"
RESULT_SUFFIX = ".result.json"
EXIT_SUFFIX = ".exit.json"  # written by the turn host when claude exits: the turn is over
INBOX = "inbox.json"  # Send-to-Claude notes waiting for the run's next turn
MODEL_SUFFIX = ".model.json"  # {wanted, ran}: the model the role asked for and the one its route gave it
ROUTE_SUFFIX = ".route"  # `plan` or `credits`: which route started the turn (read again after a restart)


class NeedsYouError(Exception):
    """The run cannot go on without kuhy; `text` names exactly what is needed, `kind` is a needs_kind."""

    def __init__(self, text: str, kind: str = "run_failed") -> None:  # noqa: D107
        super().__init__(text)
        self.kind = kind
        self.text = text


class KilledError(NeedsYouError):
    """A turn was killed again and again (signal, OOM, reboot): a manager never escalates children for it."""


def write_json(path: Path, data: object, *, durable: bool = True) -> None:  # noqa: D103
    atomic.write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n", durable=durable)


def read_json(path: Path) -> Any:  # noqa: ANN401, D103
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


CHILDREN_DIR = "children"  # an umbrella's child run dirs: <root>/<umbrella card>/children/<child id>/


def root_of(run_dir: Path) -> Path:
    """Return the run root a run dir belongs to (one level up; an umbrella child is two levels deeper)."""
    parent = run_dir.parent
    return parent.parent.parent if parent.name == CHILDREN_DIR else parent


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
    return text if text in ("plan", "credits", "free") else "plan"
