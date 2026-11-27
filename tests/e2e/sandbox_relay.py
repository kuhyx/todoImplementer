"""Relay a sandbox board to a slot build on the phone (`sandbox.py serve relay sandbox/slotN`).

A slot APK (phone_deploy from a worktree) syncs under `SYNC_NAMESPACE=sandbox/slotN`, so it never sees
kuhy's board. The sandbox server serves that namespace (T2354) signed in as the real Firebase user: the
scratch HOME gets read-only links to the three files the worker needs, nothing else of kuhy's config.
"""

from __future__ import annotations

import re
from pathlib import Path

LINKS = (
    ".config/crdt-sync/firebase.json",
    ".config/crdt-sync/password",
    ".config/todoImplementer/firebase_auth.json",
)
_NAMESPACE = re.compile(r"sandbox/[a-z0-9_-]+")


def env(work: Path, namespace: str, real_home: Path | None = None) -> dict[str, str]:
    """Link the relay's credentials into the scratch HOME; return the server env that turns the relay on."""
    if not _NAMESPACE.fullmatch(namespace):
        msg = f"relay namespace must be sandbox/<lowercase>, got {namespace!r}"
        raise SystemExit(msg)
    real = real_home or Path.home()
    for rel in LINKS:
        link = work / "home" / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(real / rel)
    return {"TODOIMPL_RELAY": "1", "TODOIMPL_RELAY_NAMESPACE": namespace}
