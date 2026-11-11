"""Throwaway server for checking the sessions page on real data: the real Router and web/dist, no board.

The backend is a bare object (only /api/sessions, /version and static files are served) and the command runner
refuses everything, so a stray click cannot open a terminal. Mark and delete would still touch ~/.claude: do not
click them against real data.

Usage: PYTHONPATH=server python3 web/dev/sessions_server.py --port 8791
"""

from __future__ import annotations

import argparse
from typing import Any

from todoimpl.http.app import make_server
from todoimpl.sessions.commands import CommandResult


class RefusingRunner:
    """Answers every command with a failure and runs nothing."""

    def run(self, argv: tuple[str, ...], timeout: float = 10.0) -> CommandResult:
        return CommandResult(argv=argv, returncode=1, stdout="", stderr="dev server: commands are disabled")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = make_server(object(), port=args.port, build="sessions-dev")  # type: ignore[arg-type]
    runner: Any = RefusingRunner()
    server.router.sessions_runner = runner
    print(f"sessions dev server on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
