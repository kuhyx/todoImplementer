"""The relay contracts (DOCS-native-app-relay.md) accept their good shapes and refuse the bad ones."""

import json
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from jsonschema import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"
DEV = "2e7ce595-0a13-48e0-9bf2-cf7282a66964"
CARD = "abcd1234-0"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def req(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "dev": DEV, "created": 1794864361000, "sent_at": 1794864360000, "body": body}


GOOD_REQUESTS = [
    req("task_start", {"card": CARD, "args": {"auto_ship": True}}),
    req("task_send", {"card": CARD, "args": {"text": "go on"}}),
    req("ask_answer", {"card": CARD, "args": {"ask": "pick", "option": "a"}}),
    req("merge_dismiss", {"group": "0123456789ab", "args": {}}),
    req("credits_fallback", {"args": {"enabled": False}}),
    req("task_detail", {"card": CARD}),
    req("task_shot", {"card": CARD, "name": "shots/a.png"}),
    req("umbrella_log", {"card": CARD, "log": "3"}),
    req("tokens", {"path": "/panel/spend", "query": "days=7"}),
    req("tokens", {"path": "", "query": ""}),
    req("live_watch", {"card": None}),
    req("snapshot_refresh", {}),
]

BAD_REQUESTS = [
    req("shell", {}),  # not in the allowlist
    req("task_start", {"args": {}}),  # no card
    req("task_start", {"card": "nope", "args": {}}),
    req("credits_fallback", {"args": {"enabled": "yes"}}),
    req("task_send", {"card": CARD, "args": {}}),  # args pinned to requests.schema.json#/$defs/send
    req("ask_answer", {"card": CARD, "args": {"option": "a"}}),
    req("task_ship", {"card": CARD, "args": {"auto_ship": True}}),
    req("merge_merge", {"group": "0123456789ab", "args": {"extra": 1}}),
    req("task_detail", {"card": CARD, "extra": 1}),
    req("tokens", {"path": "/../etc", "query": ""}),
    req("snapshot_refresh", {"x": 1}),
    {**req("task_go", {"card": CARD, "args": {}}), "dev": "pc"},  # device ids are per-install uuids
    {**req("task_go", {"card": CARD, "args": {}}), "extra": True},
]


@pytest.mark.parametrize("instance", GOOD_REQUESTS, ids=lambda r: r["kind"])
def test_relay_request_accepts(instance: dict[str, Any]) -> None:
    validate("relay-request", instance)


@pytest.mark.parametrize("instance", BAD_REQUESTS, ids=lambda r: r["kind"])
def test_relay_request_rejects(instance: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate("relay-request", instance)


def test_relay_result_ok_and_error() -> None:
    validate("relay-result", {"ok": True, "at": 1, "kind": "task_go", "data": {"task": fixture("card")}})
    validate("relay-result", {"ok": True, "at": 1, "kind": "task_shot", "data": {"png_b64": "iVBORw0KGgo="}})
    error = {
        "ok": False,
        "at": 1,
        "kind": "",
        "code": "unsealed",
        "error": "request did not open",
        "retry": False,
    }
    validate("relay-result", error)
    for bad in ({**error, "code": "nope"}, {**error, "retry": None}, {"ok": True, "at": 1, "data": {}}):
        with pytest.raises(ValidationError):
            validate("relay-result", bad)


def test_relay_tree_snapshot_nodes_reuse_the_http_shapes() -> None:
    worker = {
        "host": "pc",
        "pid": 7,
        "version": "1.0.0",
        "build": "83df521",
        "started": 1,
        "beat": 2,
        "lanes": {"act": None, "read": 0},
        "skew_ms": 3,
    }
    client = {"platform": "android", "app": "1.0.0", "build": 1, "seen": 5, "fcm": None}
    tree = {
        "meta": {"min_client": 1, "schema": 1},
        "rev": {"board": 1, "usage": 0, "sessions": 0, "merges": 0},
        "snap": {"board": fixture("board"), "usage": fixture("usage"), "sessions": fixture("sessions")},
        "presence": {"workers": {DEV: worker}, "clients": {DEV: client}},
        "watch": {DEV: {"card": CARD, "until": 9}},
    }
    validate("relay-nodes", tree)
    with pytest.raises(ValidationError):
        validate("relay-nodes", {**tree, "shell": {}})


def test_ping_is_counts_only_strings() -> None:
    ping = {"v": "1", "needs_you": "2", "failed": "1", "at": "1794864361000"}
    validate("relay-nodes", ping, "ping")
    for bad in ({**ping, "title": "x"}, {**ping, "needs_you": 2}):
        with pytest.raises(ValidationError):
            validate("relay-nodes", bad, "ping")
