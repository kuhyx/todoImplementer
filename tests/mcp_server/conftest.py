"""Fixtures: a fake /api/tokens server, and a port nothing listens on.

``mcp/`` holds the ``todoimpl_mcp`` package (its own dir, so the ``mcp`` SDK is never
shadowed); it is put on sys.path here. The SDK itself is a dev dependency
(``mcp==2.3.0``): without it these tests are skipped and the header says so.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp_fixtures import Fake, handler

URL_ENV = "TODOIMPL_TOKENS_URL"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp"))
HAVE_SDK = importlib.util.find_spec("mcp") is not None
collect_ignore_glob = [] if HAVE_SDK else ["test_*.py"]


def pytest_report_header() -> str | None:
    """Say so when the MCP tests are skipped for lack of the SDK."""
    return None if HAVE_SDK else "tests/mcp_server SKIPPED: `mcp` SDK missing (dev dep mcp==2.3.0)"


if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Fake]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    state = Fake(url)
    server.RequestHandlerClass = handler(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(URL_ENV, f"{url}/api/tokens")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the client at a port nothing listens on."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    server.server_close()
    monkeypatch.setenv(URL_ENV, f"http://127.0.0.1:{port}/api/tokens")
