"""Entry point: `python -m todoimpl.http.main [--host 127.0.0.1] [--port 8786]`."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.state import run_root
from todoimpl.relay import worker as relay

from .app import DEFAULT_DIST, make_server

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .backend import Backend

REPO = Path(__file__).resolve().parents[3]


def git_build_id(repo: Path) -> str:
    """Return `git rev-parse --short HEAD` for repo, or "unknown" when it cannot be read."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return "unknown"
    return done.stdout.strip() or "unknown" if done.returncode == 0 else "unknown"


def serve(
    backend: Backend,
    host: str = "127.0.0.1",
    port: int = 8786,
    *,
    dist: Path = DEFAULT_DIST,
    build: str | None = None,
) -> None:
    """Bind and serve until shutdown() is called on the server (or the process is stopped)."""
    build = build or git_build_id(REPO)
    server = make_server(backend, host, port, dist=dist, build=build)
    relay.start(server.router, build=build, root=run_root(), env=os.environ)  # off unless TODOIMPL_RELAY=1
    try:
        server.serve_forever()
    finally:
        server.server_close()


def load_backend() -> Backend:
    """Wire the real Scheduler, TodoClient, board and usage into one Backend (todoimpl.service)."""
    service = importlib.import_module("todoimpl.service")
    backend: Backend = service.build_backend()
    return backend


def main(argv: Sequence[str] | None = None) -> int:
    """Parse flags, wire the real backend, serve."""
    parser = argparse.ArgumentParser(prog="todoimpl.http.main", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8786)
    args = parser.parse_args(argv)
    try:
        backend = load_backend()
    except ImportError as exc:
        print(f"todoimpl: cannot wire the backend: {exc}", file=sys.stderr)
        return 2
    if (merges := getattr(backend, "merge_service", None)) is not None:
        merges.refresh_if_due()  # classify once at start, in the background
    with contextlib.suppress(KeyboardInterrupt):
        serve(backend, args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
