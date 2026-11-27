"""T2532 over real HTTP: a fake Batches API on 127.0.0.1, reached by urllib through `TODOIMPL_BATCH_URL`.

The triage classifier's background path (`batch=True`) submits, polls and reads the results JSONL; the ledger
gets a `batch` line at half the Haiku price. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest
from todoimpl.credits import batch, batchstore, ledger
from todoimpl.triage.classify import ClassifyError, claude_classifier

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SEEN: list[tuple[str, str, str]] = []


class Fake(BaseHTTPRequestHandler):
    """POST creates msgbatch_9; GET retrieve says ended; GET results gives one succeeded line."""

    custom = ""

    def log_message(self, *_args: object) -> None:
        return

    def _send(self, status: int, text: str) -> None:
        self.send_response(status)
        self.end_headers()
        self.wfile.write(text.encode())

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Fake.custom = body["requests"][0]["custom_id"]
        SEEN.append(("POST", self.path, self.headers["x-api-key"]))
        self._send(200, json.dumps({"id": "msgbatch_9", "processing_status": "in_progress"}))

    def do_GET(self) -> None:
        SEEN.append(("GET", self.path, self.headers["x-api-key"]))
        if self.path.endswith("/missing"):
            self._send(404, '{"type": "error", "error": {"type": "not_found_error"}}')
        elif self.path.endswith("/results"):
            message = {
                "content": [{"type": "text", "text": '{"label": "manual"}'}],
                "usage": {"input_tokens": 2000, "output_tokens": 400},
            }
            self._send(
                200,
                json.dumps({"custom_id": Fake.custom, "result": {"type": "succeeded", "message": message}}),
            )
        else:
            url = f"http://127.0.0.1:{self.headers['host'].rsplit(':', 1)[1]}{self.path}/results"
            self._send(
                200, json.dumps({"id": "msgbatch_9", "processing_status": "ended", "results_url": url})
            )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/messages/batches"
    monkeypatch.setenv("TODOIMPL_BATCH_URL", url)
    SEEN.clear()
    yield url
    server.shutdown()


def test_t2532_triage_tick_classifier_over_http(
    root: Path, api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch, "POLL_S", 0.0)  # poll again at once
    with pytest.raises(ClassifyError, match="batch pending"):
        claude_classifier("note: x", root, batch=True)
    assert claude_classifier("note: x", root, batch=True) == '{"label": "manual"}'
    one = "/v1/messages/batches/msgbatch_9"
    want = [("POST", "/v1/messages/batches"), ("GET", one), ("GET", one + "/results")]
    assert [s[:2] for s in SEEN] == want
    assert all(s[2].startswith("sk-ant-api03-") for s in SEEN)
    assert batchstore.pending(root) == []
    assert ledger.spent(root, 0, "batch") == pytest.approx((2000 * 0.10 + 400 * 0.50) / 1e6 * 0.5)


def test_t2532_an_http_error_status_is_a_reply(api: str) -> None:
    status, text = batch.urllib_transport("GET", api + "/missing", {}, None, 5)
    assert status == 404
    assert "not_found_error" in text
