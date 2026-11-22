"""The server's env minus its own venv, for anything that runs a target repo's tools (T1836, T2500).

The server runs from `~/src/todoImplementer/.venv`. A gate, a deploy or a turn that inherited it would run the
server's python for a bare `python3` (no user site, so kuhy's installed packages vanish), and a
`VIRTUAL_ENV`-aware installer such as `uv pip install` would write into the live server's venv.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def strip(env: Mapping[str, str]) -> dict[str, str]:
    """Return `env` without `VIRTUAL_ENV` and without the venv's `bin` (and the server's own) on `PATH`."""
    out = dict(env)
    venvs = {out.pop("VIRTUAL_ENV", "")}
    if sys.prefix != sys.base_prefix:
        venvs.add(sys.prefix)
    drop = {f"{v}/bin" for v in venvs if v}
    out["PATH"] = os.pathsep.join(
        p for p in out.get("PATH", "").split(os.pathsep) if p.rstrip("/") not in drop
    )
    return out
