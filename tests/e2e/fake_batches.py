#!/usr/bin/env python3
"""Local stand-in for the Anthropic API a sandbox board's free credits talk to (T2532 live checks).

Usage: ``fake_batches.py <out.json> <requests.jsonl> [<delay s>]``. ``out.json`` gets ``{"url": ...}`` once it
listens. Answers:

- ``GET /v1/models``: 200, so the key monitor calls the scratch key valid;
- ``POST /v1/messages/batches``: logs the request (custom_id, model, prompt head) to ``requests.jsonl``,
  returns an id;
- ``GET /v1/messages/batches/<id>``: ``in_progress`` until ``delay`` seconds passed, then ``ended``;
- ``GET /v1/messages/batches/<id>/results``: one ``succeeded`` row: a merge prompt gets ``{"groups": []}``,
  any other (a triage prompt) a `manual` verdict, so nothing it labels starts work.

No key is checked and nothing leaves the machine.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BATCHES = "/v1/messages/batches"
USAGE = {"input_tokens": 2000, "output_tokens": 100}
_LOCK = threading.Lock()


def _answer(prompt: str) -> str:
    if '"groups"' in prompt:
        return json.dumps({"groups": []})
    return json.dumps({"label": "manual", "reason": "an errand for kuhy (fake batch)"})


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def _send(self, code: int, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != BATCHES:
            self._send(404, '{"type":"error"}')
            return
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))) or b"{}")
        one = body["requests"][0]
        prompt = one["params"]["messages"][0]["content"]
        with _LOCK:
            found = f"msgbatch_fake{len(self.server.batches) + 1:04d}"
            self.server.batches[found] = (time.time(), one["custom_id"], prompt)
            row = {
                "id": found,
                "custom_id": one["custom_id"],
                "model": one["params"]["model"],
                "head": prompt[:80],
            }
            with self.server.log.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row) + "\n")
        self._send(200, json.dumps({"id": found, "processing_status": "in_progress"}))

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._send(200, '{"data": []}')
            return
        parts = self.path.removeprefix(BATCHES + "/").split("/")
        with _LOCK:
            found = self.server.batches.get(parts[0])
        if not self.path.startswith(BATCHES + "/") or found is None:
            self._send(404, '{"type":"error"}')
            return
        at, custom, prompt = found
        base = f"http://127.0.0.1:{self.server.server_port}{BATCHES}/{parts[0]}"
        if parts[1:] == ["results"]:
            message = {"content": [{"type": "text", "text": _answer(prompt)}], "usage": USAGE}
            self._send(
                200, json.dumps({"custom_id": custom, "result": {"type": "succeeded", "message": message}})
            )
            return
        done = time.time() - at >= self.server.delay
        state = {"id": parts[0], "processing_status": "ended" if done else "in_progress"}
        self._send(200, json.dumps({**state, "results_url": f"{base}/results" if done else None}))

    def log_message(self, *_args: object) -> None:
        pass


class _Server(ThreadingHTTPServer):
    def __init__(self, log: Path, delay: float) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.log, self.delay = log, delay
        self.batches: dict[str, tuple[float, str, str]] = {}


def main(argv: list[str]) -> int:
    """Listen, publish the URL, serve until killed."""
    server = _Server(Path(argv[1]), float(argv[2]) if len(argv) > 2 else 0.0)
    out = Path(argv[0])
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}"}), encoding="utf-8")
    tmp.replace(out)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
