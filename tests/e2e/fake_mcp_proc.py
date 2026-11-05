"""Standalone fake todo MCP for the e2e harness: seed notes, publish the URL, run until killed.

Usage: ``fake_mcp_proc.py <notes.json> <out.json>`` with ``tests/shims`` on PYTHONPATH. ``out.json``
is written (atomically) once the server listens: ``{"url": ..., "ids": [note id, ...]}``.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from fake_todo_mcp import FakeTodoMcp


def main(argv: list[str]) -> int:
    """Seed, publish, then block; the harness stops this process at teardown."""
    notes = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out = Path(argv[1])
    fake = FakeTodoMcp().start()
    ids = []
    for note in notes:
        if note.get("sections"):
            ids.append(fake.seed_sections(note["repo"], [(title, body) for title, body in note["sections"]]))
        else:
            ids.append(
                fake.seed(note["repo"], note["title"], note["body"], done_check=note.get("done_check"))
            )
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps({"url": fake.url, "ids": ids}), encoding="utf-8")
    tmp.replace(out)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
