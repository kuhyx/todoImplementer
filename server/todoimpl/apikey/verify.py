"""Live key check: GET /v1/models (costs no tokens). A $0 credit balance never makes a key invalid."""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

MODELS_URL = "https://api.anthropic.com/v1/models"
API_VERSION = "2023-06-01"
REJECTED_TYPES = frozenset({"authentication_error", "permission_error"})
VALID_TYPES = frozenset({"billing_error"})
HTTP_OK = 200
Transport = Callable[[str, dict[str, str], float], tuple[int, str]]
Outcome = Literal["valid", "invalid", "check_failed"]


@dataclass(frozen=True)
class Verdict:
    """What the live check concluded; `detail` is safe to show (it never contains the key)."""

    outcome: Outcome
    detail: str


def urllib_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    """GET url; an HTTP error status is a normal reply, a network failure raises OSError."""
    request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 - fixed https URL
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
            return reply.status, reply.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(65536).decode("utf-8", "replace")


def _error(body: str) -> tuple[str, str]:
    """Return the (type, message) of an Anthropic error body, ("", "") when it is not one."""
    try:
        data = json.loads(body)["error"]
        return str(data["type"]), str(data.get("message", ""))
    except ValueError, KeyError, TypeError:
        return "", ""


def verify(
    key: str, transport: Transport = urllib_transport, *, url: str | None = None, timeout: float = 10.0
) -> Verdict:
    """Classify the key: valid (200), invalid (rejected), check_failed (network, 5xx, anything else).

    `url` defaults to `$TODOIMPL_MODELS_URL` (a sandbox's local fake), else the real models endpoint.
    """
    url = url or os.environ.get("TODOIMPL_MODELS_URL") or MODELS_URL
    headers = {"x-api-key": key, "anthropic-version": API_VERSION}
    try:
        code, body = transport(url, headers, timeout)
    except (OSError, http.client.HTTPException) as error:
        return Verdict("check_failed", f"{type(error).__name__}: {str(error).replace(key, '***')}")
    kind, message = _error(body)
    if code == HTTP_OK or kind in VALID_TYPES or "credit balance" in message.lower():
        return Verdict("valid", "key accepted")
    if code in (401, 403) or kind in REJECTED_TYPES:
        return Verdict("invalid", f"HTTP {code}")
    return Verdict("check_failed", f"HTTP {code}")
