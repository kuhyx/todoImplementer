"""A python user site of its own for each turn (T2495).

A worker that ran `pip install -e .` in its worktree used to write to kuhy's real user site
(`~/.local/lib/python3.X/site-packages`, read by `/usr/bin/python3`). The live lock services run from it,
so the worker's install silently changed what production runs. Each turn now gets
`PYTHONUSERBASE=<run dir>/userbase`: `pip install` and `pip install --user` land there, and the run's cleanup
deletes it with the run.

The real site must stay visible (the worker runs the repo's tests and gates against kuhy's installed packages,
and an editable install is a `.pth` file that works only from a site dir, never from PYTHONPATH). So for every
`pythonX.Y` the real base has a site for, the turn's base gets the same site dir holding one `.pth` that calls
`site.addsitedir(<real site>)`. That processes the real site's own `.pth` files too, and appends the real site
right after the turn's own: a package the worker installs shadows the real one, only inside that turn.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

USERBASE_VAR = "PYTHONUSERBASE"
DIR = "userbase"  # under the run dir, so the run's cleanup removes it
PTH = "todoimpl-userbase.pth"


def real_base(env: Mapping[str, str]) -> Path:
    """Return kuhy's user base: the one the server's env sets, else `~/.local`."""
    found = env.get(USERBASE_VAR)
    return Path(found) if found else Path(env.get("HOME") or Path.home()) / ".local"


def pth_line(real_site: Path) -> str:
    """Return the `.pth` text that adds `real_site` (and its own `.pth` files) to the path."""
    return f"import site; site.addsitedir({str(real_site)!r})\n"


def _put(path: Path, text: str) -> None:
    """Write `path` only when it differs: a running turn's python may be reading it."""
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def ensure(run_dir: Path, real: Path) -> Path:
    """Create the turn's user base under `run_dir` (idempotent) and return it."""
    base = run_dir / DIR
    base.mkdir(parents=True, exist_ok=True)
    for site in sorted(real.glob("lib/python*/site-packages")):
        mine = base / site.relative_to(real)
        mine.mkdir(parents=True, exist_ok=True)
        _put(mine / PTH, pth_line(site))
    return base


def turn_env(run_dir: Path, env: Mapping[str, str], real: Path | None = None) -> dict[str, str]:
    """Return the env a turn adds: its own `PYTHONUSERBASE` (`real` defaults to kuhy's, read from `env`)."""
    return {USERBASE_VAR: str(ensure(run_dir, real or real_base(env)))}
