"""Fixtures for the usage tests: real-shaped stream-json lines in a temp run root."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

if TYPE_CHECKING:
    from collections.abc import Callable


def _result(cost: float, session: str = "s-1") -> dict[str, Any]:
    """Build a stream-json `result` event."""
    return {
        "type": "result",
        "subtype": "success",
        "total_cost_usd": cost,
        "num_turns": 3,
        "session_id": session,
        "result": "done",
    }


def _rate(window: str = "seven_day", **over: Any) -> dict[str, Any]:
    """Build a rate_limit_event shaped like one captured from a real session."""
    info: dict[str, Any] = {
        "status": "allowed_warning",
        "resetsAt": 1788000000,
        "rateLimitType": window,
        "utilization": 0.77,
        "overageStatus": "rejected",
        "isUsingOverage": False,
        "unifiedWindows": {
            "five_hour": {"utilization": 0.12, "resetsAt": 1787900000, "status": "allowed"},
            "seven_day": {"utilization": 0.77, "resetsAt": 1788000000, "status": "allowed_warning"},
        },
    }
    info.update(over)
    return {"type": "rate_limit_event", "rate_limit_info": info}


@pytest.fixture
def write_stream() -> Callable[[Path, str, list[Any], float | None], Path]:
    """Write events (dicts, or raw strings) to <dir>/<name>.stream.jsonl; optionally set mtime."""

    def _write(directory: Path, name: str, events: list[Any], mtime: float | None = None) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.stream.jsonl"
        path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in events) + "\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    return _write


@pytest.fixture(scope="session")
def usage_validator() -> Any:
    """Return a draft 2020-12 validator for contracts/usage.schema.json (refs resolved from contracts/)."""
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    registry: Registry = Registry()
    for f in contracts.glob("*.schema.json"):
        data = json.loads(f.read_text())
        registry = registry.with_resource(data["$id"], Resource.from_contents(data))
    schema = json.loads((contracts / "usage.schema.json").read_text())
    return Draft202012Validator(schema, registry=registry)


@pytest.fixture
def result() -> Callable[..., dict[str, Any]]:
    """Return the result-event builder."""
    return _result


@pytest.fixture
def rate() -> Callable[..., dict[str, Any]]:
    """Return the rate_limit_event builder."""
    return _rate
