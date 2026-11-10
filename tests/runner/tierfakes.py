"""The cheap tier's outside world: a fake OmniRoute gateway, free-llm-check-dir and claude-free shims."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from runnerfakes import Env, executable

if TYPE_CHECKING:
    from pathlib import Path

KEY = "omni-test-key"


class Free:
    """`public` and `up` flip the verdicts; `asked` records every checked directory and gateway call."""

    def __init__(self, world: Env) -> None:
        self.up = True
        self.asked: list[str] = []
        self.auth: list[str | None] = []
        self._log = world.tmp / "check-dir.log"
        self._flag = world.tmp / "private"
        self._world = world
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.auth.append(self.headers.get("Authorization"))
                self.send_response(200 if owner.up else 503)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args: object) -> None:
                """Keep the output quiet."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        script = f'#!/bin/sh\necho "$1" >> "{self._log}"\n[ ! -e "{self._flag}" ]\n'
        executable(world.bin / "free-llm-check-dir", script)
        executable(world.bin / "claude-free", "#!/bin/sh\nexit 0\n")
        key = world.home / ".config" / "omniroute" / "api_key"
        key.parent.mkdir(parents=True)
        key.write_text(KEY + "\n", encoding="utf-8")

    @property
    def public(self) -> bool:
        """Whether free-llm-check-dir approves the directory (the shim reads a flag file)."""
        return not self._flag.exists()

    @public.setter
    def public(self, value: bool) -> None:
        if value:
            self._flag.unlink(missing_ok=True)
        else:
            self._flag.touch()

    def checked(self) -> list[str]:
        """Directories handed to free-llm-check-dir so far."""
        return self._log.read_text(encoding="utf-8").split() if self._log.exists() else []

    def remove_tools(self) -> None:
        """Make claude-free and free-llm-check-dir vanish from the shim dir."""
        (self._world.bin / "claude-free").unlink()
        (self._world.bin / "free-llm-check-dir").unlink()

    def stop(self) -> None:
        """Shut the gateway down."""
        self._server.shutdown()
        self._server.server_close()


def worktree_of(world: Env) -> Path:
    """Return a throwaway directory standing in for a worktree."""
    path = world.tmp / "wt-probe"
    path.mkdir(exist_ok=True)
    return path
