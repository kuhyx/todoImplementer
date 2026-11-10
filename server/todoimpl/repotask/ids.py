"""The id of a repo task: stable per repo, whatever notes the repo has, shaped like every other card id."""

from __future__ import annotations

import hashlib

HASH_LEN = 8


def norm(repo: str) -> str:
    """Return the key two spellings of one repo share (case and outer blanks do not matter)."""
    return repo.strip().lower()


def repo_card_id(repo: str) -> str:
    """Return `<8 hex of sha1(repo)>-0`: the card id, run-dir name and branch suffix of the repo's task."""
    return f"{hashlib.sha1(norm(repo).encode(), usedforsecurity=False).hexdigest()[:HASH_LEN]}-0"
