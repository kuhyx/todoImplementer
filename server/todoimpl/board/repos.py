"""Where a note's repo is cloned: the one rule the board's repo check and the runner's repo_dir share."""

from __future__ import annotations

import os
import re
from pathlib import Path

_FOUND: dict[tuple[Path, str], Path] = {}  # (src root, repo) -> clone found by origin URL
_ORIGIN = re.compile(r'\[remote "origin"\][^\[]*?^\s*url\s*=\s*(\S+)', re.MULTILINE)


def _origin_matches(clone: Path, repo: str) -> bool:
    """Say whether the clone origin URL ends in `<owner>/<name>` (https or ssh, optional .git)."""
    try:
        config = (clone / ".git" / "config").read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return False
    found = _ORIGIN.search(config)
    if found is None:
        return False
    url = found.group(1).removesuffix(".git")
    return url.endswith((f"/{repo}", f":{repo}"))


def _scan(base: Path, repo: str) -> Path | None:
    """One level of `<base>/*/` for a checkout of `repo`; a vanished clone drops out of the cache."""
    cached = _FOUND.get((base, repo))
    if cached is not None and (cached / ".git").exists():
        return cached
    _FOUND.pop((base, repo), None)
    try:
        children = sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        return None
    for child in children:
        if _origin_matches(child, repo):
            _FOUND[(base, repo)] = child
            return child
    return None


def repo_path(repo: str, src_root: Path | None = None) -> Path:
    """Return the clone of `owner/name`: `<src root>/<name>`, else the checkout whose origin is that repo.

    The root defaults to $TODOIMPL_SRC, ~/src. A missing clone still yields `<root>/<name>`.
    """
    base = src_root or Path(os.environ.get("TODOIMPL_SRC") or Path.home() / "src")
    direct = base / repo.rpartition("/")[2]
    if direct.exists() or "/" not in repo:
        return direct
    return _scan(base, repo) or direct
