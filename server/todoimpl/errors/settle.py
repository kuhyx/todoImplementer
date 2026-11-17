"""After a Ship: tell the error's source it is fixed and record which build holds the fix.

A fix counts as shipped only when its deploy passed (Ship deploys before it closes), so `shipped_at` is also
the time the fixed build reached the phone. `fixed_build` is the build that holds the fix (the source's
`build` hook on the pushed commit); 0 when nobody can tell.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.worktree import repo_dir

from . import ledger, sources

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

log = logging.getLogger("todoimpl.errors")


def _build(source: sources.Source, entry: Mapping[str, Any]) -> int:
    try:
        checkout = repo_dir(str(entry.get("repo", "")))
    except NeedsYouError:  # not cloned here: the build stays unknown
        return 0
    return sources.build_of(source, checkout, str(entry.get("commit", "")))


def settle(root: Path, owners: Mapping[str, sources.Source]) -> None:
    """Resolve every `shipped` entry at its source (by app); a failing hook is retried on the next tick."""
    for key, entry in ledger.load(root).items():
        if entry.get("state") != "shipped":
            continue
        source = owners.get(key.partition(":")[0])
        if source is not None and not sources.resolve(source, key.partition(":")[2]):
            log.warning("error %s: the resolve hook of %s failed, trying again", key, source.app)
            continue
        build = _build(source, entry) if source is not None else 0
        ledger.put(root, key, state="fixed", fixed_build=build, installed_at=entry.get("shipped_at", 0))
