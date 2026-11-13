"""GET /api/live (SSE) over a real socket."""

import json
import socket
import time
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call


def read_sse(live: Live, path: str, headers: dict[str, str] | None = None) -> tuple[str, str]:
    with socket.create_connection(("127.0.0.1", live.port), timeout=5) as sock:
        extra = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{live.port}\r\nConnection: close\r\n{extra}\r\n".encode()
        )
        data = b""
        while chunk := sock.recv(4096):
            data += chunk
    head, _, body = data.decode().partition("\r\n\r\n")
    return head, body


def sse_payloads(body: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_live_streams_snapshot_then_events_and_matches_contract(live: Live) -> None:
    live.backend.events = [
        {"type": "activity", "seq": 1, "at": 1.0, "kind": "text", "text": "a", "tool": None},
        {"type": "activity", "seq": 2, "at": 2.0, "kind": "tool", "text": "b", "tool": "Bash"},
        {"type": "done", "status": "needs_you"},
    ]
    head, body = read_sse(live, f"/api/live?id={live.backend.task_id}", {"Last-Event-ID": "1"})
    assert "200" in head.splitlines()[0]
    lowered = head.lower()
    assert "content-type: text/event-stream" in lowered
    assert "cache-control: no-store" in lowered
    payloads = sse_payloads(body)
    assert [p["type"] for p in payloads] == ["stage", "activity", "done"]
    assert payloads[1]["seq"] == 2
    for p in payloads:
        validate("live", p)
    card = live.backend.task_data["card"]
    assert payloads[0]["stage"] == card["stage"]
    assert payloads[0]["actions"] == card["actions"]


@pytest.mark.parametrize("path", ["/api/live", "/api/live?id=short", "/api/live?id=a&id=b"])
def test_live_needs_one_valid_id(live: Live, path: str) -> None:
    assert call(live.port, "GET", path).status == 400


def test_live_unknown_task_is_404(live: Live) -> None:
    assert call(live.port, "GET", "/api/live?id=zzzzzzzz-0").status == 404


@pytest.mark.parametrize("value", ["abc", "-3"])
def test_live_ignores_a_garbage_last_event_id(live: Live, value: str) -> None:
    live.backend.events = [
        {"type": "activity", "seq": 1, "at": 1.0, "kind": "text", "text": "a", "tool": None}
    ]
    _, body = read_sse(live, f"/api/live?id={live.backend.task_id}", {"Last-Event-ID": value})
    assert [p["type"] for p in sse_payloads(body)] == ["stage", "activity"]


def test_live_client_hangup_is_swallowed(live: Live) -> None:
    live.backend.events = [{"type": "cost", "cost_usd": 1.0}] * 200
    sock = socket.create_connection(("127.0.0.1", live.port), timeout=5)
    sock.sendall(
        f"GET /api/live?id={live.backend.task_id} HTTP/1.1\r\nHost: 127.0.0.1:{live.port}\r\n\r\n".encode()
    )
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
    sock.close()
    time.sleep(0.2)
    assert call(live.port, "GET", "/version").status == 200


def test_client_reset_during_plain_response_is_swallowed(live: Live) -> None:
    sock = socket.create_connection(("127.0.0.1", live.port), timeout=5)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
    sock.sendall(f"GET /api/board HTTP/1.1\r\nHost: 127.0.0.1:{live.port}\r\n\r\n".encode())
    sock.close()
    time.sleep(0.2)
    assert call(live.port, "GET", "/version").status == 200


def test_t104_snapshot_of_a_card_never_run_matches_contract(live: Live) -> None:
    card = live.backend.task_data["card"]
    card.update(stage=None, status="backlog", column="backlog", current="not started", needs=None)
    live.backend.events = [{"type": "done", "status": "backlog"}]
    _, body = read_sse(live, f"/api/live?id={live.backend.task_id}")
    snapshot = sse_payloads(body)[0]
    assert snapshot["stage"] is None
    validate("live", snapshot)
