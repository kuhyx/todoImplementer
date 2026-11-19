"""POST /api/task/<id>/model: the picker's click, over the page and the relay (T2218)."""

import json

from contract_lib import CONTRACTS, validate
from httpfakes import Live, post
from todoimpl import modelpick
from todoimpl.http import bodies
from todoimpl.relay.kinds import ROUTED

DEV = "0123abcd-0000-4000-8000-00000000beef"  # an install uuid


def test_t2218_the_picker_posts_a_known_model_or_default_and_nothing_else(live: Live) -> None:
    for model in modelpick.IDS:
        assert post(live, "model", {"model": model}).status == 200
    assert post(live, "model", {"model": "claude-gpt-5"}).status == 400
    assert live.backend.calls == [("model", live.backend.task_id, m) for m in modelpick.IDS]


def test_t2218_the_relay_kind_and_the_contracts_name_the_same_models() -> None:
    assert "task_model" in ROUTED
    body = {"card": "abcd1234-0", "args": {"model": "default"}}
    validate("relay-request", {"kind": "task_model", "dev": DEV, "created": 1, "sent_at": 1, "body": body})
    assert bodies.check("model", {"model": modelpick.MODELS[0].id}) is None
    assert bodies.check("model", {}) == "body must be exactly {model}"
    schema = json.loads((CONTRACTS / "requests.schema.json").read_text(encoding="utf-8"))
    enum = schema["$defs"]["model"]["properties"]["model"]["enum"]
    assert tuple(enum) == modelpick.IDS
