"""The allowlist is the contract's, write kinds land on POST routes, guard 2 agrees with the schema."""

import json
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from jsonschema import ValidationError
from relayfakes import DEV, req
from test_parity import bodies
from todoimpl.http import asks, merge, newtask, sessions, settings
from todoimpl.http.routes import ACTION_PATH
from todoimpl.relay import envelope, kinds

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
CARD = "abcd1234-0"
POST_ROUTES = (ACTION_PATH, asks.POST_PATH, merge.POST_PATH, sessions.POST_PATH)


def schema_kinds() -> set[str]:
    schema = json.loads((CONTRACTS / "relay-request.schema.json").read_text(encoding="utf-8"))
    return set(schema["$defs"]["kind"]["enum"])


def test_the_allowlist_is_the_contracts() -> None:
    assert set(kinds.ALL) == schema_kinds()
    assert len(kinds.ALL) == len(set(kinds.ALL)) == 32


def test_lanes() -> None:
    assert kinds.lane_of("task_go") == "act"
    assert kinds.lane_of("session_delete") == "act"
    assert kinds.lane_of("task_detail") == "read"
    assert kinds.lane_of("live_watch") == "read"


@pytest.mark.parametrize("kind", sorted(k for k, v in kinds.ROUTED.items() if v.lane == "act"))
def test_each_write_kind_posts_to_a_real_route(kind: str) -> None:
    call = kinds.ROUTED[kind].call(bodies(CARD)[kind])
    assert call.method == "POST"
    assert call.target in {newtask.PATH, settings.PATH} or any(r.fullmatch(call.target) for r in POST_ROUTES)


def test_tokens_and_logs_keep_their_parts_in_place() -> None:
    assert (
        kinds.ROUTED["tokens"].call({"path": "/panel", "query": "days=7"}).target
        == "/api/tokens/panel?days=7"
    )
    assert kinds.ROUTED["tokens"].call({"path": "", "query": ""}).target == "/api/tokens"
    log = kinds.ROUTED["umbrella_log"].call({"card": CARD, "log": "a?b#c"}).target
    assert log == f"/api/umbrella/{CARD}/log/a%3Fb%23c"


def schema_ok(request: dict[str, Any]) -> bool:
    try:
        validate("relay-request", request)
    except ValidationError:
        return False
    return True


SID = "11111111-2222-4333-8444-555555555555"
VALID_ARGS: dict[str, dict[str, Any]] = {
    "session_mark": {"args": {"id": SID, "mark": "done"}},
    "session_delete": {"args": {"ids": [SID]}},
}
SKIP = {"new_task", "session_resume"}  # their args need more than this test builds; the route checks them
GOOD = [req(k, VALID_ARGS.get(k, b)) for k, b in bodies(CARD).items() if k not in SKIP]
GOOD += [req("live_watch", {"card": None}), req("live_watch", {"card": CARD}), req("snapshot_refresh", {})]
BAD = [
    req("task_start", {"args": {}}),
    req("task_start", {"card": "nope", "args": {}}),
    req("task_go", {"card": CARD, "args": {}}, dev="pc"),
    req("task_go", {"card": CARD, "args": {}}, extra=True),
    req("task_go", {"card": CARD, "args": {}}, sent_at=-1),
    req("task_detail", {"card": CARD, "extra": 1}),
    req("merge_merge", {"group": "0123456789ab", "args": {"extra": 1}}),
    req("tokens", {"path": "/../etc", "query": ""}),
    req("task_shot", {"card": CARD, "name": "a.jpg"}),
    req("umbrella_log", {"card": CARD, "log": "a/b"}),
    req("live_watch", {"card": 7}),
    req("notify_test", {"x": 1}),
]


@pytest.mark.parametrize("request_", GOOD + BAD, ids=lambda r: str(r["kind"]))
def test_guard2_agrees_with_the_schema(request_: dict[str, Any]) -> None:
    assert (envelope.problem(envelope.normalized(request_)) is None) == schema_ok(request_)


def test_empty_objects_dropped_by_rtdb_read_as_empty() -> None:
    sent = {
        "kind": "task_go",
        "dev": DEV,
        "sent_at": 1,
    }  # body {"card", "args": {}} lost its args, here all of it
    assert envelope.normalized(sent)["body"] == {"args": {}}
    assert envelope.normalized({**sent, "kind": "snapshot_refresh"})["body"] == {}
    assert envelope.normalized({**sent, "body": "x"})["body"] == "x"
