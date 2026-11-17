"""Replies the Router gives in every shape become result data or a refusal with the contract's code."""

import pytest
from httpfakes import FakeBackend
from rtdb_relay.server import RequestError
from todoimpl.http.reply import Reply, json_reply
from todoimpl.http.routes import Router
from todoimpl.relay import bridge
from todoimpl.relay.kinds import Call


def test_a_stream_route_is_not_relayed(router: Router, backend: FakeBackend) -> None:
    with pytest.raises(RequestError) as err:
        bridge.send(router, Call("GET", f"/api/live?id={backend.task_id}"))
    assert err.value.code == "internal"


@pytest.mark.parametrize(
    ("reply", "code", "message", "retry"),
    [
        (Reply(502, b"<html>bad gateway</html>"), "upstream_unavailable", "HTTP 502", True),
        (Reply(418, b"[]"), "internal", "HTTP 418", True),
        (json_reply({"error": "no such panel"}, 404), "not_found", "no such panel", False),
        (
            json_reply({"ok": False, "error": {"code": "disabled", "message": ""}}, 409),
            "disabled",
            "HTTP 409",
            False,
        ),
    ],
)
def test_refusals(reply: Reply, code: str, message: str, retry: bool) -> None:
    with pytest.raises(RequestError) as err:
        bridge.data_of(reply)
    assert (err.value.code, err.value.message, err.value.retry) == (code, message, retry)


def test_data_shapes() -> None:
    assert bridge.data_of(json_reply({"ok": True, "task": 1})) == {"task": 1}
    assert bridge.data_of(json_reply([1, 2])) == {"data": [1, 2]}
    assert bridge.data_of(Reply(200, b"a\nb", "application/x-ndjson")) == {"text": "a\nb"}
    assert bridge.data_of(Reply(200, b"\x01", "image/png")) == {"png_b64": "AQ=="}
