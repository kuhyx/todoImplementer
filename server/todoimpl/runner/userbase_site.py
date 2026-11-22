"""Run from a turn's user site at python start: add kuhy's real site behind the turn's own (T2495, T2502).

`userbase.ensure` copies this file into each turn site as `_todoimpl_userbase.py`, next to a `.pth` that calls
`add(<real site>)`; stdlib only, since it runs in whatever python the worker starts. `site.addsitedir` puts
the real site (and its own `.pth` files) on `sys.path` after the turn's. A plain package the worker installs
is found first that way, but an editable one is a finder that setuptools appends to `sys.meta_path` after
`PathFinder`, so a plain copy in the real site would still win (gatelock). `add` therefore moves the finders
defined in the turn's site before `PathFinder`: whatever the worker installs shadows the real package, only
inside that turn.
"""

from __future__ import annotations

import site
import sys
from importlib.machinery import PathFinder
from pathlib import Path

MODULE = "_todoimpl_userbase"  # the name this file has inside a turn site


def _defined_in(finder: object, mine: Path) -> bool:
    """Return True when `finder`'s module is a file in the turn's site dir `mine`."""
    module = sys.modules.get(getattr(finder, "__module__", "") or "")
    found = getattr(module, "__file__", None)
    return bool(found) and Path(str(found)).parent == mine


def add(real_site: str, mine: Path | None = None) -> None:
    """Add `real_site` behind the turn's site, then let the turn's own finders answer before `PathFinder`."""
    here = mine or Path(__file__).parent
    site.addsitedir(real_site)
    own = [f for f in sys.meta_path if _defined_in(f, here)]
    rest = [f for f in sys.meta_path if f not in own]
    at = rest.index(PathFinder) if PathFinder in rest else len(rest)
    sys.meta_path[:] = rest[:at] + own + rest[at:]
