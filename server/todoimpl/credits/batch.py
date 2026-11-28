"""The Message Batches API on the free credit key (T2532): create, retrieve and results, nothing else.

kuhy (2026-11-27): background one-shots run here at half price when the credits are `ready`, the week's pace
has room and no purchased balance is written down (`credits_purchased_usd`); anything else goes to `claude -p`
on the plan. Raw HTTPS through the stdlib, as `apikey/verify.py` does: the `anthropic` package is no allowed
runtime dependency. The key is read in-process and sent only as the `x-api-key` header, never to a shell,
env or argv. `$TODOIMPL_BATCH_URL` points the client at a local fake (sandbox checks); tests set `TRANSPORT`.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from todoimpl.apikey import store

from . import errors, marks, pacing, route, setting

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

API = "https://api.anthropic.com/v1/messages/batches"
VERSION = "2023-06-01"
TIMEOUT_S = 10.0  # every create, retrieve and results call
POLL_S = 60.0  # a pending batch is asked about at most once a minute
MAX_TOKENS = 4000  # Haiku 5.5 thinks by default: room for the thinking and the JSON reply
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
EXHAUSTED_S = 3600.0  # a billing error rests the credits an hour; the key monitor knows better later
HTTP_OK = 200

Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, str]]


class BatchError(Exception):
    """A batch call failed: the caller goes to the plan instead."""


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> tuple[int, str]:
    """Send one request; an HTTP error status is a normal reply, a network failure raises OSError."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - API URL
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
            return reply.status, reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(65536).decode("utf-8", "replace")


TRANSPORT: Transport = urllib_transport


def base() -> str:  # noqa: D103
    return os.environ.get("TODOIMPL_BATCH_URL") or API


def model_id(model: str) -> str:
    """Return the API id of a CLI alias (`haiku` -> claude-haiku-5-5); a full id passes through."""
    return MODELS.get(model, model)


def refusal(root: Path, now: float) -> str | None:
    """Return why no batch may go out now (logged when it is purchased balance), None when one may."""
    if (bought := setting.purchased_usd()) > 0:
        why = f"purchased credit on the account (${bought:g}): batches spend only the free grant"
        log.warning("batch refused: %s", why)
        return why
    state, text = route.state_of(root, now)
    if state != "ready":
        return text
    return route.CAPPED_TEXT if pacing.pace(root, now).over_cap else None


def _json(text: str) -> Any:  # noqa: ANN401 - parsed JSON
    try:
        return json.loads(text)
    except ValueError as exc:
        msg = f"batch reply is no JSON: {text[:200]!r}"
        raise BatchError(msg) from exc


def _headers() -> dict[str, str]:
    key = store.read_key()
    if key is None:
        msg = "no API key"
        raise BatchError(msg)
    return {"x-api-key": key, "anthropic-version": VERSION, "content-type": "application/json"}


def _call(  # noqa: PLR0913, PLR0917 - one request
    root: Path,
    method: str,
    url: str,
    body: dict[str, Any] | None,
    transport: Transport,
    now: float | None = None,
) -> str:
    data = None if body is None else json.dumps(body).encode()
    try:
        status, text = transport(method, url, _headers(), data, TIMEOUT_S)
    except OSError as exc:
        msg = f"batch {method} failed: {exc}"
        raise BatchError(msg) from exc
    if status != HTTP_OK:
        if errors.balance_low(text):
            setting.turn_off(errors.BALANCE_REASON, now or time.time())
        elif errors.exhausted(text):
            marks.mark_exhausted(root, (now or time.time()) + EXHAUSTED_S, f"batch: {text[:200]}")
        msg = f"batch {method} answered {status}: {text[:200]}"
        raise BatchError(msg)
    return text


def submit(  # noqa: PLR0913, PLR0917 - one request
    root: Path, custom_id: str, prompt: str, model: str, transport: Transport, now: float | None = None
) -> str:
    """Create a one-request batch; return its id."""
    params = {
        "model": model_id(model), "max_tokens": MAX_TOKENS, "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": prompt}],
    }  # fmt: skip
    text = _call(
        root, "POST", base(), {"requests": [{"custom_id": custom_id, "params": params}]}, transport, now
    )
    data = _json(text)
    found = data.get("id") if isinstance(data, dict) else None
    if not isinstance(found, str):
        msg = f"batch create gave no id: {text[:200]}"
        raise BatchError(msg)
    return found


def retrieve(root: Path, batch_id: str, transport: Transport) -> dict[str, Any]:
    """Return the batch object (`processing_status`, `results_url`)."""
    data = _json(_call(root, "GET", f"{base()}/{batch_id}", None, transport))
    return data if isinstance(data, dict) else {}


def result(root: Path, url: str, custom_id: str, transport: Transport) -> tuple[str, str, dict[str, Any]]:
    """Return (result type, text of the text blocks, usage) of `custom_id` in the results JSONL."""
    for line in _call(root, "GET", url, None, transport).splitlines():
        row = _json(line) if line.strip() else {}
        if not isinstance(row, dict) or row.get("custom_id") != custom_id:
            continue
        res = row.get("result") or {}
        message = res.get("message") or {}
        blocks = message.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        return str(res.get("type")), text, message.get("usage") or {}
    return "missing", "", {}
