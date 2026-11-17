"""The contract record: parse, key, and the schema."""

from __future__ import annotations

import pytest
from contract_lib import validate
from errfakes import rec
from jsonschema import ValidationError
from todoimpl.errors.record import AppError, parse


def test_a_contract_record_parses_and_keys_by_app_and_signature() -> None:
    found = parse(rec())
    assert isinstance(found, AppError)
    assert found.key == "kartka:02b0d43d9f"
    assert (found.count, found.build, found.open) == (3, 41, True)
    assert found.version_name == "1.4.0-abc1234"


@pytest.mark.parametrize(
    "bad",
    [
        "text",
        rec(app=""),
        rec(signature="has space"),
        rec(count=0),
        rec(count="3"),
        rec(build=-1),
        rec(build=True),
        rec(repo="norepo"),
        rec(top_frame=5),
        rec(open="yes"),
        {k: v for k, v in rec().items() if k != "kind"},
    ],
)
def test_a_malformed_record_is_none(bad: object) -> None:
    assert parse(bad) is None


def test_optional_fields_default_and_open_can_be_false() -> None:
    minimal = {k: v for k, v in rec().items() if k not in ("top_frame", "version_name", "detail")}
    found = parse({**minimal, "open": False})
    assert found is not None
    assert (found.top_frame, found.version_name, found.detail, found.open) == (None, None, None, False)


def test_the_schema_takes_a_record_and_a_report_and_refuses_a_stray_key() -> None:
    validate("app-error", rec(), "record")
    validate("app-error", {"version": 1, "errors": [rec()]}, "report")
    with pytest.raises(ValidationError):
        validate("app-error", {**rec(), "extra": 1}, "record")
    with pytest.raises(ValidationError):
        validate("app-error", rec(count=0), "record")


def test_the_schema_takes_a_source_and_a_ledger() -> None:
    source = {"app": "kartka", "repo": "kuhyx/kartka", "adapter": "kartka", "path": "~/x"}
    validate("app-error", source, "source")
    entry = {"state": "ticket", "repo": "kuhyx/kartka", "title": "t", "count": 1, "starts": 0}
    validate("app-error", {"kartka:1": entry}, "ledger")
    with pytest.raises(ValidationError):
        validate("app-error", {"kartka:1": {**entry, "state": "weird"}}, "ledger")
