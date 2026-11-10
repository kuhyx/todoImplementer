"""Streamable-HTTP transport against the fake server (JSON and SSE reply modes)."""

from __future__ import annotations

import socket

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import TodoError
from todoimpl.todo_mcp.transport import Transport


def test_handshake_then_call(fake: FakeTodoMcp) -> None:
    fake.seed("kuhyx/a", "a todos")
    text = Transport(fake.url, fake.token).call_tool("list_tasks", {})
    assert text.endswith("a todos\tkuhy")
    assert fake.methods == ["initialize", "notifications/initialized", "tools/call"]


def test_session_reused_across_calls(fake: FakeTodoMcp) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})
    transport.call_tool("list_tasks", {})
    assert fake.methods.count("initialize") == 1
    assert len(fake.sessions) == 1


def test_works_without_session_header() -> None:
    with FakeTodoMcp(session=False) as fake:
        assert Transport(fake.url, fake.token).call_tool("list_tasks", {}) == "no tasks match"


def test_expired_session_reinitialises_once(fake: FakeTodoMcp) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})
    fake.expire_sessions()
    assert transport.call_tool("list_tasks", {}) == "no tasks match"
    assert fake.methods.count("initialize") == 2


def test_session_404_twice_is_error(fake: FakeTodoMcp) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})
    fake.fail_method("tools/call", 404)
    with pytest.raises(TodoError, match="session"):
        transport.call_tool("list_tasks", {})
    assert fake.methods.count("initialize") == 2


def test_bad_token_is_auth_error(fake: FakeTodoMcp) -> None:
    with pytest.raises(TodoError, match="HTTP 401"):
        Transport(fake.url, "wrong").call_tool("list_tasks", {})


def test_server_error_status(fake: FakeTodoMcp) -> None:
    fake.fail_next(503)
    with pytest.raises(TodoError, match="HTTP 503"):
        Transport(fake.url, fake.token).call_tool("list_tasks", {})


def test_initialized_notification_rejected(fake: FakeTodoMcp) -> None:
    fake.fail_method("notifications/initialized", 500)
    with pytest.raises(TodoError, match="HTTP 500"):
        Transport(fake.url, fake.token).call_tool("list_tasks", {})


def test_connection_refused() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(TodoError, match="cannot reach"):
        Transport(f"http://127.0.0.1:{port}/mcp", "t", timeout=2).call_tool("list_tasks", {})


def test_tool_error_result(fake: FakeTodoMcp) -> None:
    with pytest.raises(TodoError, match="id: required"):
        Transport(fake.url, fake.token).call_tool("get_task", {})


def test_rpc_error(fake: FakeTodoMcp) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})
    with pytest.raises(TodoError, match="method not found"):
        transport.request("bogus/method", {})


def test_initialize_error_reply(fake: FakeTodoMcp) -> None:
    fake.force_raw(b'{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"nope"}}')
    with pytest.raises(TodoError, match="nope"):
        Transport(fake.url, fake.token).call_tool("list_tasks", {})


_ID3 = b'"jsonrpc":"2.0","id":3'


@pytest.mark.parametrize(
    ("body", "ctype", "match"),
    [
        (b"not json", "application/json", "unparseable"),
        (b"[1]", "application/json", "unparseable"),
        (b'{"jsonrpc":"2.0","id":999,"result":{}}', "application/json", "unparseable"),
        (b"event: message\ndata: {oops\n\n", "text/event-stream", "unparseable"),
        (b"event: message\ndata: [1]\n\n", "text/event-stream", "unparseable"),
        (b"{" + _ID3 + b"}", "application/json", "no result"),
        (b"{" + _ID3 + b',"result":{"content":"x"}}', "application/json", "content"),
        (b"{" + _ID3 + b',"result":{"content":[{"type":"image"}]}}', "application/json", "no text"),
        (b"{" + _ID3 + b',"error":{"code":1}}', "application/json", "rpc error"),
        (b"{" + _ID3 + b',"result":{}}', "application/json", "content"),
    ],
)
def test_bad_replies(fake: FakeTodoMcp, body: bytes, ctype: str, match: str) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})  # ids 1 (initialize) and 2 are used
    fake.force_raw(body, ctype)
    with pytest.raises(TodoError, match=match):
        transport.call_tool("list_tasks", {})


def test_multi_text_items_joined(fake: FakeTodoMcp) -> None:
    transport = Transport(fake.url, fake.token)
    transport.call_tool("list_tasks", {})
    items = b'[{"type":"text","text":"a"},{"type":"text","text":"b"}]'
    fake.force_raw(b"{" + _ID3 + b',"result":{"content":' + items + b"}}")
    assert transport.call_tool("list_tasks", {}) == "a\nb"
