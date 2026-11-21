"""The loopback /api/peer endpoint over a real server: own token, no browser path, refusals with reasons."""

from __future__ import annotations

import http.client
import json
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from peerfakes import CARD, make_world

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "http"))
from httpfakes import FakeBackend  # noqa: E402
from todoimpl.http.app import make_server  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from peerfakes import World

TOKEN = "secret-token"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[World, int]]:
    world = make_world(tmp_path)
    backend = FakeBackend()
    backend.peer_hub = world.hub  # type: ignore[attr-defined]
    server = make_server(backend, port=0, dist=tmp_path / "dist")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield world, server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(5)


def call(port: int, route: str, body: object, **headers: str) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    sent = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if "token" not in headers:
        sent["X-Todoimpl-Peer-Token"] = TOKEN
    sent |= {k.replace("_", "-"): v for k, v in headers.items() if k != "token"}
    if headers.get("token"):
        sent["X-Todoimpl-Peer-Token"] = headers["token"]
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    conn.request("POST", f"/api/peer/{route}", body=raw, headers=sent)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


def test_send_await_reply_round_trip(served: tuple[World, int]) -> None:
    world, port = served
    status, sent = call(port, "send", {"label": "leetcode-guard", "to": CARD, "text": "port?"})
    assert status == 200, sent
    msg_id, sender = sent["message"]["id"], sent["sender"]
    world.hub.tick()
    key = world.hub.card_key(CARD)
    status, got = call(port, "reply", {"card": CARD, "card_key": key, "id": msg_id, "text": "8790"})
    assert status == 200, got
    status, waited = call(port, "await", {"label": "leetcode-guard", "sender": sender, "id": msg_id, "timeout": 1})
    assert (status, waited["message"]["reply"]) == (200, "8790")
    status, empty = call(port, "inbox", {"label": "leetcode-guard", "sender": sender, "wait": 0})
    assert (status, empty["messages"]) == (200, [])


@pytest.mark.parametrize(
    ("body", "headers", "status", "why"),
    [
        ({"label": "a", "to": CARD, "text": "x"}, {"token": "wrong"}, 403, "bad peer token"),
        ({"label": "a", "to": CARD, "text": "x"}, {"token": ""}, 403, "bad peer token"),
        ({"label": "a", "to": CARD, "text": "x"}, {"Origin": "http://127.0.0.1:8786"}, 403, "browser"),
        ({"label": "a", "to": CARD, "text": "x"}, {"X_Forwarded_For": "1.2.3.4"}, 403, "loopback"),
        ({"to": CARD, "text": "x"}, {}, 400, "label is required"),
        ({"label": "a", "to": CARD}, {}, 400, "text"),
        ({"label": "a", "to": CARD, "text": "x", "reply_to": 5}, {}, 400, "reply_to"),
        ({"label": "a", "id": 3}, {}, 400, "id"),
        ([1], {}, 400, "JSON object"),
        (b"{nope", {}, 400, "JSON object"),
        ({"label": "a", "to": "zzzz9999-0", "text": "x"}, {}, 404, "unknown task"),
    ],
)
def test_refusals(
    served: tuple[World, int], body: object, headers: dict[str, str], status: int, why: str
) -> None:
    world, port = served
    route = "await" if isinstance(body, dict) and "id" in body else "send"
    got_status, got = call(port, route, body, **headers)
    assert got_status == status
    assert why in got["error"]["message"]
    assert world.hub.thread(CARD) == []


def test_refusal_carries_retry_after(served: tuple[World, int]) -> None:
    world, port = served
    world.pipe.open.clear()
    for n in range(5):
        call(port, "send", {"label": f"s{n}", "to": CARD, "text": "x"})
    status, got = call(port, "send", {"label": "late", "to": CARD, "text": "x"})
    assert status == 409
    assert got["retry_after"] == 5.0


def test_public_host_and_unknown_route_are_refused(served: tuple[World, int]) -> None:
    _, port = served
    status, _ = call(port, "nope", {"label": "a"})
    assert status == 404
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/api/peer/send", body=b"{}", headers={"Host": "agents.kuhy.duckdns.org"})
    assert conn.getresponse().status in {401, 403, 423}
    conn.close()


def test_big_body_is_refused(served: tuple[World, int]) -> None:
    _, port = served
    status, got = call(port, "send", b"x" * (70 * 1024))
    assert status == 400
    assert "too large" in got["error"]["message"]


def test_no_hub_means_no_route(tmp_path: Path) -> None:
    server = make_server(FakeBackend(), port=0, dist=tmp_path / "dist")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        status, _ = call(server.server_address[1], "send", {"label": "a", "to": CARD, "text": "x"})
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_answers_and_the_card_thread_match_the_contract(served: tuple[World, int], tmp_path: Path) -> None:
    from contract_lib import validate  # noqa: PLC0415
    from todoimpl.peer.book import thread_of  # noqa: PLC0415

    world, port = served
    _, sent = call(port, "send", {"label": "desk", "to": CARD, "text": "q"})
    validate("peer", sent)
    world.hub.tick()
    _, answered = call(port, "reply", {"card": CARD, "card_key": world.hub.card_key(CARD), "id": sent["message"]["id"], "text": "a"})
    validate("peer", answered)
    _, box = call(port, "inbox", {"label": "desk", "sender": sent["sender"]})
    validate("peer", box)
    task = world.hub.task_sender(CARD)
    world.hub.send(task, f"desk#{sent['sender']}", "back")
    _, box = call(port, "inbox", {"label": "desk", "sender": sent["sender"]})
    assert box["messages"]
    validate("peer", box)
    _, refused = call(port, "send", {"label": "desk", "to": "zzzz9999-0", "text": "x"})
    validate("peer", refused)
    thread = thread_of(tmp_path / CARD)
    assert [m["state"] for m in thread] == ["answered", "delivered"]
    validate("peer", thread, "thread")
    assert thread_of(tmp_path / "nothing") == []
