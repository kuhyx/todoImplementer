"""Raw gateway answers to the `free` object: states, quotas, the chain, today's tokens, no secrets."""

from __future__ import annotations

import json
from typing import Any

from gatewayfakes import MASKED, NOW, connection, iso, world
from todoimpl.gateway import snapshot
from todoimpl.gateway.monitor import ours_tokens

RAW_KEYS = {
    "health": "/api/v1/models/health",
    "providers": "/api/providers",
    "combos": "/api/combos",
    "metrics": "/api/combos/metrics",
    "analytics": "/api/usage/analytics?period=day",
}


def raw() -> dict[str, Any]:
    answers = world(NOW)
    out = {key: answers[path] for key, path in RAW_KEYS.items()}
    out["quotas"] = {"id-openrouter": answers["/api/usage/id-openrouter"]}
    return out


def test_provider_states_cooldown_failing_off_and_ok() -> None:
    body = snapshot.build(raw(), NOW)
    states = {p["id"]: (p["state"], p["until"]) for p in body["providers"]}
    assert states["nvidia"] == ("ok", None)
    assert states["groq"][0] == "cooling"
    assert abs(states["groq"][1] - (NOW + 90)) < 1
    assert states["xkiro"] == ("failing", None)
    assert states["agnes"] == ("off", None)
    assert body["counts"] == {"providers": 5, "ok": 2, "cooling": 1, "failing": 2, "quota_known": 1}


def test_a_cooldown_that_has_passed_is_not_cooling() -> None:
    past = {"apiKeyHealth": {"k": {"cooldownUntil": iso(NOW - 10)}}, "rateLimitedUntil": "not a time"}
    state, until = snapshot.connection_state(connection("a", providerSpecificData=past), NOW)
    assert (state, until) == ("ok", None)
    assert snapshot.connection_state(connection("a", rateLimitedUntil=iso(NOW + 5)), NOW)[0] == "cooling"


def test_the_worst_connection_of_a_provider_names_its_state() -> None:
    both = {"connections": [connection("a"), connection("a", testStatus="error"), "junk", connection("a")]}
    (row,) = snapshot.build({"providers": both}, NOW)["providers"]
    assert row["state"] == "failing"


def test_only_a_real_limit_becomes_a_quota() -> None:
    body = snapshot.build(raw(), NOW)
    (quota,) = body["quotas"]
    assert (quota["provider"], quota["label"], quota["used"], quota["total"]) == (
        "openrouter",
        "free_daily",
        46,
        50,
    )
    assert quota["left_pct"] == 8.0
    assert (
        abs(quota["reset_at"] - (NOW + 3600)) < 1
    )  # the zero-total credits and the unlimited rpm are dropped
    assert [p["quota"] for p in body["providers"] if p["id"] == "openrouter"] == [True]


def test_the_chain_follows_the_combo_order_with_the_state_of_each_link() -> None:
    combo = snapshot.build(raw(), NOW)["combo"]
    assert combo["name"] == "free-best"
    assert (combo["requests"], combo["ok_pct"], combo["fallback_pct"]) == (114, 99, 36)
    assert [(s["provider"], s["state"]) for s in combo["steps"]] == [
        ("nvidia", "ok"),
        ("groq", "cooling"),
        ("openrouter", "failing"),  # its last call was an error
    ]
    assert combo["steps"][0]["requests"] == 48
    assert combo["steps"][1]["ok_pct"] is None


def test_a_link_whose_provider_is_off_is_failing() -> None:
    answers = raw()
    answers["combos"]["combos"][0]["models"][0]["providerId"] = "agnes"
    assert snapshot.build(answers, NOW)["combo"]["steps"][0]["state"] == "failing"


def test_tokens_are_the_gateway_wide_figures_of_todays_utc_date() -> None:
    assert snapshot.build(raw(), NOW, ours=1010)["tokens"] == {
        "in": 4_000_000,
        "out": 20_000,
        "requests": 163,
        "ours": 1010,
    }
    assert snapshot.build({"analytics": {"dailyTrend": []}}, NOW)["tokens"] == {
        "in": 0,
        "out": 0,
        "requests": 0,
        "ours": None,
    }


def test_model_health_counts_the_cooling_models() -> None:
    assert snapshot.build(raw(), NOW)["models"] == {"total": 2, "cooling": 1}


def test_nothing_read_gives_empty_sections_not_errors() -> None:
    body = snapshot.build({}, NOW)
    assert (body["tokens"], body["combo"], body["providers"], body["quotas"]) == (None, None, [], [])
    assert body["models"] == {"total": 0, "cooling": 0}
    assert snapshot.build({"providers": {"connections": "x"}, "combos": {"combos": []}}, NOW)["combo"] is None


def test_odd_shapes_are_survived() -> None:
    odd = {
        "quotas": {"a": [], "b": {"quotas": {"q": 1}}},
        "metrics": [],
        "health": {"data": [1, {"state": "ok"}]},
    }
    assert snapshot.build(odd, NOW)["quotas"] == []
    assert snapshot.parse_time(5) is None
    assert snapshot.parse_time("5") is None


def test_no_secret_field_reaches_the_output() -> None:
    text = json.dumps(snapshot.build(raw(), NOW, ours=1))
    for secret in ("apiKey", MASKED, "ab12cd34", "acct-77", "accountId", "providerSpecificData", "id-nvidia"):
        assert secret not in text


def test_ours_counts_only_calls_inside_a_worker_window() -> None:
    calls = world(NOW)["/api/usage/call-logs?limit=300"]
    assert ours_tokens(calls, [(NOW - 20, NOW)]) == 1010
    assert ours_tokens(calls, [(NOW - 20, NOW), (NOW - 5100, NOW - 4900)]) == 1024
    assert ours_tokens(calls, [(0.0, 1.0)]) == 0
    assert ours_tokens(calls, []) is None
    assert ours_tokens("not a list", [(0.0, 1.0)]) == 0
