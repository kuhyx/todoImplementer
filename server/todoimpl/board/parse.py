"""Strict field readers for state.json; every failure is a StateError naming the field."""

from __future__ import annotations

from typing import Any


class StateError(ValueError):
    """state.json exists but is not a valid run state."""


def typed(data: dict[str, Any], key: str, kind: type | tuple[type, ...], default: Any = None) -> Any:  # noqa: ANN401
    """Return data[key] if it has the type; the default when absent (required when default is None)."""
    if key not in data:
        if default is None:
            msg = f"state.json: missing {key!r}"
            raise StateError(msg)
        return default
    value = data[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        msg = f"state.json: {key!r} has the wrong type"
        raise StateError(msg)
    return value


def opt(data: dict[str, Any], key: str, kind: type | tuple[type, ...]) -> Any:  # noqa: ANN401
    """Return data[key] (None when absent or null) if it has the type."""
    return None if data.get(key) is None else typed(data, key, kind)


def choice(data: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    """Return data[key], which must be one of `allowed`."""
    value = typed(data, key, str)
    if value not in allowed:
        msg = f"state.json: {key!r} is {value!r}, expected one of {', '.join(allowed)}"
        raise StateError(msg)
    return str(value)


def opt_choice(data: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str | None:
    """Like `choice` but null/absent gives None."""
    return None if data.get(key) is None else choice(data, key, allowed)


def listed(data: dict[str, Any], key: str) -> list[Any]:
    """Return data[key] as a list (absent gives an empty one)."""
    return list(typed(data, key, list, []))


def item(kind: type, key: str, raw: object) -> Any:  # noqa: ANN401
    """Build a SpecQuestion/Evidence from a dict, naming the list on a bad entry."""
    if not isinstance(raw, dict):
        msg = f"state.json: {key!r} holds a non-object"
        raise StateError(msg)
    try:
        return kind(**raw)
    except TypeError as exc:
        msg = f"state.json: bad entry in {key!r}: {exc}"
        raise StateError(msg) from exc
