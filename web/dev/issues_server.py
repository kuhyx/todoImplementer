"""Throwaway server for checking the issues page on a real log: the real Router and web/dist, no board.

The backend answers only `issues(id8)`: the given file for the given task id, None (404) for any other id.
Every other route of the board fails, so nothing is started or changed.

Usage: PYTHONPATH=server python3 web/dev/issues_server.py --port 8797 --task 2556952d-0 --log /tmp/x/free-issues.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from todoimpl.http.app import make_server


class IssuesOnly:
    """The one backend call the issues page makes."""

    def __init__(self, task: str, log: Path) -> None:
        self.task = task
        self.log = log

    def issues(self, id8: str) -> str | None:
        """Serve the log for the known task, re-read on every request so appended lines show on the next poll."""
        return self.log.read_text(encoding="utf-8") if id8 == self.task else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    server = make_server(IssuesOnly(args.task, args.log), port=args.port, build="issues-dev")  # type: ignore[arg-type]
    print(f"issues dev server on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
