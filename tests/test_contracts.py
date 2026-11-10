"""The contracts are valid schemas and their sample fixtures (shared with the web tests) validate."""

import json
from pathlib import Path
from typing import Any

import pytest
from contract_lib import CONTRACTS, validate
from jsonschema import Draft202012Validator, ValidationError

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMAS = sorted(CONTRACTS.glob("*.schema.json"))


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_schema_is_valid_2020_12(path: Path) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 250


@pytest.mark.parametrize("name", ["state", "board", "task", "usage", "version", "track"])
def test_fixture_validates(name: str) -> None:
    validate(name, fixture(name))


def test_card_fixture_validates_as_card() -> None:
    validate("common", fixture("card"), "task_card")


def test_state_requires_core_fields() -> None:
    state = fixture("state")
    del state["stage"]
    with pytest.raises(ValidationError):
        validate("state", state)


def test_state_tolerates_extra_keys() -> None:
    validate("state", {**fixture("state"), "future_key": 1})


def test_state_takes_the_cheap_tier_keys_and_rejects_a_bad_tier() -> None:
    tiered = {
        **fixture("state"),
        "tier": "cheap",
        "free_models": True,
        "escalated": True,
        "escalate_reason": "x",
    }
    validate("state", tiered)
    with pytest.raises(ValidationError):
        validate("state", {**tiered, "tier": "pricey"})


def test_card_requires_the_tier_badges() -> None:
    card = fixture("card")
    broken = {**card, "tier": {"cheap": True}}
    with pytest.raises(ValidationError):
        validate("task", {**fixture("task"), "card": broken})


def test_unknown_status_is_rejected() -> None:
    card = {**fixture("card"), "status": "mostly_done"}
    with pytest.raises(ValidationError):
        validate("common", card, "task_card")


def test_disabled_action_needs_a_reason() -> None:
    action = {"id": "ship", "label": "Ship", "enabled": False, "reason": None}
    with pytest.raises(ValidationError):
        validate("common", action, "action")
    validate("common", {**action, "reason": "not at the gate"}, "action")


def test_board_has_five_columns() -> None:
    board = fixture("board")
    board["columns"] = board["columns"][:4]
    with pytest.raises(ValidationError):
        validate("board", board)


@pytest.mark.parametrize(
    ("fragment", "body"),
    [
        ("start", {}),
        ("spec_answers", {"answers": {"Q1": "yes"}}),
        ("spec_ok", {}),
        ("send", {"text": "hi"}),
        ("ship", {}),
        ("cancel", {}),
        ("credits_fallback", {"enabled": False}),
        ("go", {}),
        ("rerun", {}),
        ("lesson_approve", {"lesson_id": "l1"}),
    ],
)
def test_request_bodies_accept_valid(fragment: str, body: dict[str, Any]) -> None:
    validate("requests", body, fragment)


@pytest.mark.parametrize(
    ("fragment", "body"),
    [
        ("start", {"x": 1}),
        ("go", {"x": 1}),
        ("spec_answers", {"answers": {}}),
        ("spec_answers", {"answers": {"foo": "x"}}),
        ("send", {"text": ""}),
        ("lesson_approve", {}),
    ],
)
def test_request_bodies_reject_invalid(fragment: str, body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate("requests", body, fragment)


def test_response_ok_and_error() -> None:
    validate("response", {"ok": True, "task": fixture("card")})
    validate("response", {"ok": False, "error": {"code": "disabled", "message": "usage limit until 09:00"}})
    with pytest.raises(ValidationError):
        validate("response", {"ok": True})


LIVE_EVENTS = [
    {"type": "activity", "seq": 1, "at": 1.0, "kind": "tool", "text": "ran make", "tool": "Bash"},
    {
        "type": "stage",
        "stage": "checks",
        "status": "working",
        "column": "running",
        "current": "checks",
        "needs": None,
        "actions": [],
    },
    {"type": "cost", "cost_usd": 0.5},
    {"type": "done", "status": "ready_to_ship"},
]


@pytest.mark.parametrize("event", LIVE_EVENTS, ids=lambda e: str(e["type"]))
def test_live_events_validate(event: dict[str, Any]) -> None:
    validate("live", event)


def test_live_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        validate("live", {"type": "mystery"})


@pytest.mark.parametrize("stage", ["review", "verify"])
def test_dropped_stages_are_rejected(stage: str) -> None:
    with pytest.raises(ValidationError):
        validate("state", {**fixture("state"), "stage": stage})


@pytest.mark.parametrize("bad", ["c59d2588", "c59d2588-", "c59d-0", "c59d2588-x"])
def test_card_id_must_be_item_id(bad: str) -> None:
    with pytest.raises(ValidationError):
        validate("common", {**fixture("card"), "id": bad}, "task_card")


def test_checks_record_needs_command_exit_tail() -> None:
    state = fixture("state")
    del state["checks"]["results"][0]["tail"]
    with pytest.raises(ValidationError):
        validate("state", state)


def test_board_error_banner_is_optional_and_typed() -> None:
    board = fixture("board")
    validate("board", board)
    validate("board", {**board, "error": None})
    validate(
        "board", {**board, "error": {"code": "upstream_unavailable", "message": "todo MCP is unreachable"}}
    )
    with pytest.raises(ValidationError):
        validate("board", {**board, "error": {"code": "nope", "message": "x"}})
