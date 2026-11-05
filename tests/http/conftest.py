"""A real server on port 0 over a FakeBackend and a scratch web/dist."""

import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

# --import-mode=importlib (pyproject) does not put this directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from httpfakes import INDEX, FakeBackend, Live
from todoimpl.http.app import make_server


@pytest.fixture
def live(tmp_path: Path) -> Iterator[Live]:
    dist = tmp_path / "dist"
    (dist / "_astro").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "_astro" / "app.js").write_text("console.log(1)", encoding="utf-8")
    backend = FakeBackend()
    server = make_server(backend, port=0, dist=dist, build="abc1234")
    server.heartbeat = 0.05
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield Live(server, backend, dist, server.router.token, port)
    server.shutdown()
    server.server_close()
    thread.join(5)
