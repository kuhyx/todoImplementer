"""Static server for a usage-page build: real /api/tokens from the old API (read-only GETs), items from the fixture.

Usage: usage_server.py --dist DIR [--port 4398] [--upstream http://127.0.0.1:8760]
Mirrors the real server's CSP (default-src 'self') so inline styles or scripts fail here too.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'"
TYPES = {
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
}
ITEMS = Path(__file__).resolve().parent.parent / "src" / "usage" / "fixtures" / "items.json"


class Handler(BaseHTTPRequestHandler):
    dist = Path()
    upstream = ""

    def _send(self, status: int, body: bytes, kind: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError, ConnectionResetError:
            return

    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        if path == "/version":
            self._send(200, b'{"build":"usagemock"}', "application/json")
        elif path == "/api/tokens/items":
            self._send(200, ITEMS.read_bytes(), "application/json")
        elif path.startswith("/api/tokens"):
            self._proxy(path, query)
        else:
            self._static(path)

    def _proxy(self, path: str, query: str) -> None:
        url = f"{self.upstream}{path}" + (f"?{query}" if query else "")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                self._send(response.status, response.read(), "application/json")
        except urllib.error.HTTPError as error:
            self._send(error.code, error.read(), "application/json")
        except OSError as error:
            self._send(502, json.dumps({"error": str(error)}).encode(), "application/json")

    def _static(self, path: str) -> None:
        relative = path.strip("/") or "index.html"
        target = (self.dist / relative).resolve()
        if target.is_dir():
            target /= "index.html"
        if not target.is_relative_to(self.dist) or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        body = target.read_bytes()
        if target.suffix == ".html":
            body = body.replace(b"__TODOIMPL_BUILD__", b"usagemock").replace(b"__TODOIMPL_CSRF__", b"mock")
        self._send(200, body, TYPES.get(target.suffix, "application/octet-stream"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True)
    parser.add_argument("--port", type=int, default=4398)
    parser.add_argument("--upstream", default="http://127.0.0.1:8760")
    args = parser.parse_args()
    Handler.dist = Path(args.dist).resolve()
    Handler.upstream = args.upstream.rstrip("/")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
