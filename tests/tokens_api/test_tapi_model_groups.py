"""Model ids collapse into Free / Haiku / Opus / Sonnet on the usage page (server side)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, Any

import pytest
import tokfix_detail as fd
import tokfix_tokens as fx
from todoimpl.tokens_api import db, model_group, router

if TYPE_CHECKING:
    from pathlib import Path

T0 = fx.T0
NEMOTRON = "nvidia/nemotron-3.5-super-vl:free"
MISTRAL = "mistralai/mistral-large-2512"
HAIKU_OLD = "claude-haiku-4-5-20251001"
HAIKU_NEW = "claude-haiku-5-5"
FABLE = "claude-fable-5-1"
EXTRA = [
    ("f1", NEMOTRON, 0.0),
    ("f2", MISTRAL, 0.0),
    ("h1", HAIKU_OLD, 1.0),
    ("h2", HAIKU_NEW, 2.0),
    ("o1", "claude-opus-5", 5.0),
    ("s9", "claude-sonnet-5", 1.5),
    ("x1", FABLE, 9.0),
]


@pytest.fixture
def store(sysroot: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(router, "_now", lambda: T0 + 2 * fx.DAY)
    path = fx.build(sysroot / "home/tester" / db.STORE)
    fd.insert(
        path,
        turns=[
            fd.turn_detail(key=k, ts=T0 + 10 + i, model=m, latency_s=2.0) for i, (k, m, _) in enumerate(EXTRA)
        ],
    )
    with closing(sqlite3.connect(path)) as conn:
        conn.executemany(
            "INSERT INTO turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [fx._turn(k, T0 + 10 + i, usd, model=m) for i, (k, m, usd) in enumerate(EXTRA)],
        )
        conn.execute(
            "INSERT INTO session_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("m1", "/home/tester", "mix", T0 + 5, T0 + 9, 1, 1, 3.0, 3.0, 0.0, 3, 1, 0,
             json.dumps({HAIKU_OLD: 1.0, HAIKU_NEW: 2.0, NEMOTRON: 0.0}), None),
        )  # fmt: skip
        conn.commit()
    return path


def _panel(name: str, query: str = "") -> dict[str, Any]:
    _, payload = router.route(["panel", name], query)
    return payload


def test_t1927_group_of_names_the_four_groups() -> None:
    assert model_group.group_of(NEMOTRON) == "Free"
    assert model_group.group_of(MISTRAL) == "Free"
    assert model_group.group_of("agnes-2.5-flash") == "Free"
    assert model_group.group_of("claude-sonnet-5:free") == "Free"
    assert model_group.group_of(HAIKU_OLD) == "Haiku"
    assert model_group.group_of("anthropic/claude-opus-5-5") == "Opus"
    assert model_group.group_of("claude-sonnet-5-5") == "Sonnet"
    assert model_group.group_of(FABLE) == FABLE
    assert model_group.group_of("<synthetic>") == "<synthetic>"


def test_t1927_dropdown_lists_the_groups_not_raw_ids(store: Path) -> None:
    _, index = router.route([], "")
    assert index["options"]["models"] == ["Free", "Haiku", "Opus", "Sonnet", FABLE]


def test_t1927_spend_by_model_sums_each_group(store: Path) -> None:
    rows = {r["model"]: r["usd"] for r in _panel("spend_more", "from=2026-09-01&to=2026-09-30")["by_model"]}
    assert rows == {"Opus": 12.0, "Sonnet": 4.5, "Haiku": 3.0, "Free": 0.0, FABLE: 9.0}


def test_t1927_latency_models_are_grouped(store: Path) -> None:
    models = {r["model"]: r["calls"] for r in _panel("latency")["models"]}
    assert models["Free"] == 2
    assert models["Haiku"] == 2
    assert not any(name.startswith("claude-haiku") for name in models)


def test_t1927_model_filter_takes_a_group(store: Path) -> None:
    free = _panel("spend_more", "model=Free&from=2026-09-01&to=2026-09-30")
    assert [r["model"] for r in free["by_model"]] == ["Free"]
    haiku = _panel("sessions", "model=Haiku&from=2026-09-01&to=2026-09-30")
    assert [s["key"] for s in haiku["sessions"]] == ["m1"]
    assert haiku["sessions"][0]["models"] == {"Haiku": 3.0, "Free": 0.0}


def test_t1927_subagent_by_model_is_grouped(store: Path) -> None:
    labels = [r["label"] for r in _panel("subagents")["by_model"]]
    assert "claude-sonnet-5-5" not in labels
