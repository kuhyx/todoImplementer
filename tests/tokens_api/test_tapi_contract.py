"""Every /api/tokens route answers in the shape contracts/tokens-*.schema.json promise.

Three stores per panel: a rich one (every table non-empty), an empty one (ratios that divide by zero
become null) and the rich one under cwd/model/scope filters. The web tests validate their fixtures
against the same schemas.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
import tokfix_contract as fc
import tokfix_tokens as fx
from contract_lib import CONTRACTS, validate
from jsonschema import ValidationError
from todoimpl.tokens.items import SessionItem
from todoimpl.tokens_api import db, items, router
from todoimpl.tokens_api.registry import PANELS
from tokfix_schema import SCHEMA

if TYPE_CHECKING:
    from pathlib import Path

NOW = fx.T0 + 2 * fx.DAY
FILTERED = "cwd=/home/tester/src/a&model=claude-opus-5-5&scope=main"


def panel_file(name: str) -> str:
    """Return the tokens-panels-* contract that defines panel ``name``."""
    for path in sorted(CONTRACTS.glob("tokens-panels-*.schema.json")):
        if name in json.loads(path.read_text(encoding="utf-8"))["$defs"]:
            return path.name.removesuffix(".schema.json")
    msg = f"no contract defines panel {name}"
    raise LookupError(msg)


def _get(path: str, query: str = "") -> tuple[HTTPStatus, dict[str, Any]]:
    return router.handle(path, query)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "_now", lambda: NOW)


@pytest.fixture
def rich(sysroot: Path) -> Path:
    return fc.rich(sysroot / "home/tester" / db.STORE)


@pytest.fixture
def empty(sysroot: Path) -> Path:
    path = sysroot / "home/tester" / db.STORE
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
    return path


def _ok(path: str, query: str = "") -> dict[str, Any]:
    status, body = _get(path, query)
    assert status == HTTPStatus.OK
    return body


@pytest.mark.parametrize("query", ["", FILTERED], ids=["default", "filtered"])
@pytest.mark.parametrize("name", sorted(PANELS))
def test_rich_panel_matches_its_contract(rich: Path, name: str, query: str) -> None:
    validate(panel_file(name), _ok(f"/api/tokens/panel/{name}", query), name)


@pytest.mark.parametrize("name", sorted(PANELS))
def test_empty_panel_matches_its_contract(empty: Path, name: str) -> None:
    validate(panel_file(name), _ok(f"/api/tokens/panel/{name}"), name)


def test_every_panel_def_belongs_to_a_registered_panel() -> None:
    declared = {
        name
        for path in CONTRACTS.glob("tokens-panels-*.schema.json")
        for name in json.loads(path.read_text(encoding="utf-8"))["$defs"]
        if name not in {"base", "ts", "session_row", "ab_metric", "ab_build", "carry_row", "agent_group"}
    }
    assert declared == set(PANELS)


@pytest.mark.parametrize("store", ["rich", "empty"])
def test_index_and_schema_match_their_contracts(request: pytest.FixtureRequest, store: str) -> None:
    request.getfixturevalue(store)
    validate("tokens-index", _ok("/api/tokens"), "index")
    validate("tokens-index", _ok("/api/tokens/schema"), "schema_doc")


def test_session_context_file_and_ab_match_their_contracts(rich: Path, sysroot: Path) -> None:
    validate("tokens-detail", _ok("/api/tokens/session/s1"), "session")
    listed = str(sysroot / "home/tester/.claude/CLAUDE.md")
    validate("tokens-detail", _ok("/api/tokens/context-file", f"path={listed}"), "context_file")
    validate("tokens-detail", _ok("/api/tokens/ab"), "ab")


def test_empty_store_ab_matches_its_contract(empty: Path) -> None:
    validate("tokens-detail", _ok("/api/tokens/ab"), "ab")


def test_items_match_their_contract(rich: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    known = {
        "s1": SessionItem("s1", "abcd1234-0", "alpha", "implement"),
        "s2": SessionItem("s2", "ffff0000-1", "beta", "plan"),
    }
    monkeypatch.setattr(items, "lookup", lambda _conn: known)
    body = _ok("/api/tokens/items")
    assert body["items"]
    validate("tokens-detail", body, "items")


def test_errors_match_the_error_contract(rich: Path, sysroot: Path) -> None:
    for path, query in [
        ("/api/tokens/nosuch", ""),
        ("/api/tokens/panel/nosuch", ""),
        ("/api/tokens/session/zzz", ""),
        ("/api/tokens/context-file", "path=/etc/passwd"),
    ]:
        status, body = _get(path, query)
        assert status == HTTPStatus.NOT_FOUND
        validate("tokens-common", body, "error")


def test_missing_store_answers_with_the_error_contract() -> None:
    status, body = _get("/api/tokens")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    validate("tokens-common", body, "error")


def test_unknown_keys_and_wrong_types_are_rejected(rich: Path) -> None:
    body = _ok("/api/tokens/panel/overview")
    validate("tokens-panels-spend", body, "overview")
    for broken in (
        {**body, "surprise": 1},
        {k: v for k, v in body.items() if k != "tiles"},
        {**body, "filters": {**body["filters"], "scope": "everything"}},
    ):
        with pytest.raises(ValidationError):
            validate("tokens-panels-spend", broken, "overview")
    nulled = copy.deepcopy(body)
    nulled["tiles"]["usd"] = None
    with pytest.raises(ValidationError):
        validate("tokens-panels-spend", nulled, "overview")


def test_a_disabled_enum_value_is_rejected(rich: Path) -> None:
    body = _ok("/api/tokens/panel/levers")
    body["rows"][0]["status"] = "maybe"
    with pytest.raises(ValidationError):
        validate("tokens-panels-spend", body, "levers")
    meta = {"total": 1, "matched": 1, "shown": 1, "columns": {"c": {"kind": "enum"}}}
    with pytest.raises(ValidationError):
        validate("tokens-common", meta, "table_meta")
    validate("tokens-common", {**meta, "columns": {"c": {"kind": "enum", "values": ["a"]}}}, "table_meta")
