import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from apikeyfakes import KEY
from todoimpl.apikey import verify

Reply = tuple[int, str]


def fake(reply: Reply | Exception, seen: list[tuple[str, dict[str, str]]] | None = None) -> verify.Transport:
    def transport(url: str, headers: dict[str, str], timeout: float) -> Reply:
        if seen is not None:
            seen.append((url, headers))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return transport


def err(kind: str, message: str = "m") -> str:
    return json.dumps({"type": "error", "error": {"type": kind, "message": message}})


def test_sends_the_key_as_a_header_to_the_models_endpoint() -> None:
    seen: list[tuple[str, dict[str, str]]] = []
    assert verify.verify(KEY, fake((200, "{}"), seen)).outcome == "valid"
    url, headers = seen[0]
    assert url == "https://api.anthropic.com/v1/models"
    assert headers == {"x-api-key": KEY, "anthropic-version": "2023-06-01"}


@pytest.mark.parametrize(
    ("reply", "outcome"),
    [
        ((200, "{}"), "valid"),
        ((401, ""), "invalid"),
        ((403, "not json"), "invalid"),
        ((400, err("authentication_error")), "invalid"),
        ((418, err("permission_error")), "invalid"),
        ((400, err("invalid_request_error", "Your credit balance is too low")), "valid"),
        ((402, err("billing_error")), "valid"),
        ((400, err("invalid_request_error", "other")), "check_failed"),
        ((429, err("rate_limit_error")), "check_failed"),
        ((500, ""), "check_failed"),
        ((529, err("overloaded_error")), "check_failed"),
        ((400, "[1]"), "check_failed"),
        ((400, '{"error": 5}'), "check_failed"),
    ],
)
def test_classifies_the_reply(reply: Reply, outcome: str) -> None:
    assert verify.verify(KEY, fake(reply)).outcome == outcome


@pytest.mark.parametrize("failure", [OSError("down"), TimeoutError("slow"), ConnectionResetError("rst")])
def test_network_failure_is_check_failed_never_fine(failure: Exception) -> None:
    verdict = verify.verify(KEY, fake(failure))
    assert verdict.outcome == "check_failed"
    assert verdict.detail


def test_details_never_contain_the_key() -> None:
    body = err("authentication_error", f"bad key {KEY}")
    for reply in [(401, body), (500, body)]:
        assert KEY not in verify.verify(KEY, fake(reply)).detail
    assert KEY not in verify.verify(KEY, fake(OSError(f"tried {KEY}"))).detail


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        code = 200 if self.headers.get("x-api-key") == KEY else 401
        body = b'{"data": []}' if code == 200 else err("authentication_error").encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


def test_urllib_transport_against_a_loopback_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1/models"
    try:
        assert verify.verify(KEY, url=url).outcome == "valid"
        assert verify.verify("sk-ant-api03-" + "Z" * 90, url=url).outcome == "invalid"
    finally:
        server.shutdown()
        server.server_close()
    assert verify.verify(KEY, url=url, timeout=2).outcome == "check_failed"  # nothing listens any more
