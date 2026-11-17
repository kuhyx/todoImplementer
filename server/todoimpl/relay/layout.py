"""The tree under todoimpl/v1-e2e: which nodes stay clear, which are sealed units."""

from __future__ import annotations

from typing import Final

from crdt_sync import E2eLayout
from rtdb_relay.layout import Layout

E2E: Final = E2eLayout.of("todoimpl/v1")  # prefix todoimpl/v1-e2e, key header at todoimpl/e2e
NODES: Final = ("board", "usage", "sessions", "merges")
LAYOUT: Final = Layout(
    root=E2E.prefix,
    clear=("meta", "rev", "requests/*/claim"),
    units={
        "snap/*": frozenset(),
        "presence/workers/*": frozenset({"beat"}),
        "presence/clients/*": frozenset({"seen"}),
        "watch/*": frozenset(),
        "live/*/*": frozenset(),
        "requests/*/req": frozenset({"created"}),
        "requests/*/result": frozenset({"at"}),
    },
)
META: Final = {"min_client": 1, "schema": 1}
