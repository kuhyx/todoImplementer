"""Guard 2: the opened request against contracts/relay-request.schema.json, before anything runs.

Stdlib only, like http/bodies.py: this mirrors the envelope and the per-kind body shape (ids, names, paths).
The `args` inside a body are the HTTP route's own body, and the Router checks them with the same code it runs
for a click; tests/relay/test_envelope.py proves the two together agree with the schema.
"""

from __future__ import annotations

import re
from typing import Any, Final

from todoimpl.http.routes import CARD_ID

from . import kinds

DEV: Final = re.compile(r"[0-9a-f-]{36}")
GROUP: Final = re.compile(r"[0-9a-f]{12}")
SHOT: Final = re.compile(r"[A-Za-z0-9_./-]+\.png")
LOG: Final = re.compile(r"[^/]{1,64}")
TOKENS_PATH: Final = re.compile(r"(|/(panel|session|items|ab|context-file|schema)(/[^?#]{0,200})?)")
MAX_NAME: Final = 200
MAX_QUERY: Final = 2000
TOP: Final = frozenset({"kind", "dev", "created", "sent_at", "body"})
REQUIRED: Final = frozenset({"kind", "dev", "sent_at", "body"})


def _count(value: object) -> bool:
    """Tell whether value is a JSON integer >= 0 (bool is not one)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _text(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _shape(kind: str) -> tuple[frozenset[str], dict[str, Any]]:
    """Return the exact body keys of a kind and the checks for the keys that are not `args`."""
    card = {"card": lambda v: _text(v, CARD_ID)}
    if kind.startswith(("task_", "ask_")) and kind in kinds.ROUTED and kinds.ROUTED[kind].lane == "act":
        return frozenset({"card", "args"}), card
    shapes: dict[str, tuple[frozenset[str], dict[str, Any]]] = {
        "merge_merge": (frozenset({"group", "args"}), {"group": lambda v: _text(v, GROUP), "args": _empty}),
        "task_detail": (frozenset({"card"}), card),
        "task_issues": (frozenset({"card"}), card),
        "umbrella": (frozenset({"card"}), card),
        "task_shot": (frozenset({"card", "name"}), {**card, "name": _shot}),
        "umbrella_log": (frozenset({"card", "log"}), {**card, "log": lambda v: _text(v, LOG)}),
        "tokens": (frozenset({"path", "query"}), {"path": lambda v: _text(v, TOKENS_PATH), "query": _query}),
        "live_watch": (frozenset({"card"}), {"card": lambda v: v is None or _text(v, CARD_ID)}),
        "snapshot_refresh": (frozenset(), {}),
        "notify_test": (frozenset(), {}),
    }
    shapes["merge_dismiss"] = shapes["merge_merge"]
    return shapes.get(kind, (frozenset({"args"}), {}))  # new_task, credits_fallback, session_*


def _empty(value: object) -> bool:
    return value == {}


def _shot(value: object) -> bool:
    return isinstance(value, str) and len(value) <= MAX_NAME and SHOT.fullmatch(value) is not None


def _query(value: object) -> bool:
    return isinstance(value, str) and len(value) <= MAX_QUERY


def normalized(req: dict[str, Any]) -> dict[str, Any]:
    """Undo RTDB's pruning: missing body/args read as {}; live_watch's card, session_mark's mark as null."""
    body = req.get("body", {})
    if isinstance(body, dict) and "args" in _shape(str(req.get("kind")))[0] and "args" not in body:
        body = {**body, "args": {}}
    if isinstance(body, dict) and req.get("kind") == "live_watch" and "card" not in body:
        body = {**body, "card": None}
    args = body.get("args") if isinstance(body, dict) else None
    if req.get("kind") == "session_mark" and isinstance(args, dict) and "mark" not in args:
        body = {**body, "args": {**args, "mark": None}}  # unmark: the sealer pruned `mark: null` (T2041)
    return {**req, "body": body}


def problem(req: dict[str, Any]) -> str | None:
    """Return what makes `req` break the schema, or None. `req["kind"]` is already on the allowlist."""
    if not REQUIRED <= set(req) <= TOP:
        return "request must hold exactly kind, dev, sent_at, body (and created)"
    if not _text(req["dev"], DEV):
        return "dev must be the per-install uuid"
    if not _count(req["sent_at"]) or ("created" in req and not _count(req["created"])):
        return "sent_at and created must be counts of ms"
    return _body_problem(str(req["kind"]), req["body"])


def _body_problem(kind: str, body: object) -> str | None:
    if not isinstance(body, dict):
        return "body must be an object"
    keys, checks = _shape(kind)
    if set(body) != keys:
        return f"body must be exactly {sorted(keys)}"
    if "args" in keys and not isinstance(body["args"], dict):
        return "args must be an object"
    bad = next((key for key, ok in checks.items() if not ok(body[key])), None)
    return None if bad is None else f"{bad} is not valid"
