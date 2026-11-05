"""Filesystem seam: every absolute path this package reads goes through here.

``TODOIMPL_ROOT`` (default: empty = the real filesystem) is prefixed to every
path, so a test points the whole package at a temp tree with one env var.
``$HOME`` (not ``Path.home()``) locates user files, so a test can move home too.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = "TODOIMPL_ROOT"


def sysroot() -> str:
    """Return the configured filesystem root as a raw string ("" = real filesystem).

    A string, not a Path: ``Path("")`` normalises to ``Path(".")``.
    """
    return os.environ.get(ROOT_ENV, "")


def sysroot_path(absolute: str) -> Path:
    """Resolve an absolute system path underneath the configured root."""
    root = sysroot()
    return Path(root) / absolute.lstrip("/") if root else Path(absolute)


def user_path(relative: str) -> Path:
    """Resolve a path relative to the invoking user's home, under the root."""
    home = os.environ.get("HOME", "/root")
    return sysroot_path(f"{home.rstrip('/')}/{relative.lstrip('/')}")
