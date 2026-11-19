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


def former_human_id(repo: str) -> str:
    """Return `<same 8 hex>-1`: the card the repo's MANUAL WORK REQUIRED parts had from T1980 to T2114.

    No card has this id any more; its run dir still holds the answers kuhy gave there (`foldasks`).
    """
    return repo_card_id(repo).removesuffix("-0") + "-1"
