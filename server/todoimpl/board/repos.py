"""Where a note's repo is cloned: the one rule the board's repo check and the runner's repo_dir share."""

from __future__ import annotations

import os
from pathlib import Path


def repo_path(repo: str, src_root: Path | None = None) -> Path:
    """Return `<src root>/<name>` for `owner/name` (or a bare name); root defaults to $TODOIMPL_SRC, ~/src."""
    base = src_root or Path(os.environ.get("TODOIMPL_SRC") or Path.home() / "src")
    return base / repo.rpartition("/")[2]
