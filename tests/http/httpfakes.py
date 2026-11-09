"""Fake Backend and a tiny HTTP client shared by the http tests."""

import copy
import http.client
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from todoimpl.http.app import AppServer

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
POST_ACTIONS = (
    "start",
    "spec-answers",
    "spec-ok",
    "send",
    "ship",
    "close",
    "cancel",
    "lesson-approve",
    "go",
    "rerun",
)


def load(name: str) -> dict[str, Any]:
    """Return the sample fixture shared with the contract tests."""
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def all_actions() -> list[dict[str, Any]]:
    """Every POST action, enabled."""
    return [{"id": a, "label": a, "enabled": True, "reason": None} for a in POST_ACTIONS]


class FakeBackend:
    """In-memory Backend recording every action call."""

    def __init__(self) -> None:
        self.board_data = load("board")
        self.task_data = load("task")
        self.task_data["card"]["actions"] = all_actions()
        self.usage_data = load("usage")
        self.events: list[dict[str, Any]] = []
        self.calls: list[tuple[Any, ...]] = []
        self.failure: Exception | None = None
        self.hang = False
        self.shots: dict[str, bytes] = {}
        self.issues_text = ""

    @property
    def task_id(self) -> str:
        """Id of the only known task."""
        return str(self.task_data["card"]["id"])

    def _maybe_fail(self) -> None:
        if self.failure is not None:
            raise self.failure

    def board(self) -> dict[str, Any]:
        self._maybe_fail()
        return self.board_data

    def task(self, id8: str) -> dict[str, Any] | None:
        self._maybe_fail()
        return copy.deepcopy(self.task_data) if id8 == self.task_id else None

    def shot(self, id8: str, name: str) -> bytes | None:
        self._maybe_fail()
        self.calls.append(("shot", id8, name))
        return self.shots.get(name) if id8 == self.task_id else None

    def issues(self, id8: str) -> str | None:
        self._maybe_fail()
        self.calls.append(("issues", id8))
        return self.issues_text if id8 == self.task_id else None

    def usage(self) -> dict[str, Any]:
        self._maybe_fail()
        return self.usage_data

    def subscribe(self, id8: str) -> Iterator[dict[str, Any]]:
        self.calls.append(("subscribe", id8))
        yield from self.events

    def _record(self, *call: Any) -> None:
        self._maybe_fail()
        self.calls.append(call)

    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        self._record("start", id8, auto_ship)

    def spec_answers(self, id8: str, answers: dict[str, str]) -> None:
        self._record("spec_answers", id8, answers)

    def spec_ok(self, id8: str) -> None:
        self._record("spec_ok", id8)

    def send(self, id8: str, text: str) -> None:
        self._record("send", id8, text)

    def ship(self, id8: str) -> None:
        self._record("ship", id8)

    def close(self, id8: str) -> None:
        self._record("close", id8)

    def cancel(self, id8: str) -> None:
        self._record("cancel", id8)

    def set_credits_fallback(self, *, enabled: bool) -> dict[str, Any]:
        self.calls.append(("set_credits_fallback", str(enabled)))
        return {"enabled": enabled, "state": "ready" if enabled else "off", "text": "fake"}

    def go(self, id8: str) -> None:
        self._record("go", id8)

    def rerun(self, id8: str) -> None:
        self._record("rerun", id8)

    def lesson_approve(self, id8: str, lesson_id: str) -> None:
        self._record("lesson_approve", id8, lesson_id)


class Reply:
    """A parsed HTTP answer."""

    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        """Decode the body as JSON."""
        return json.loads(self.body)


def call(
    port: int,
    method: str,
    path: str,
    body: bytes | str | dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Reply:
    """One request on a fresh connection."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload: bytes | None
    if isinstance(body, dict):
        payload = json.dumps(body).encode()
    elif isinstance(body, str):
        payload = body.encode()
    else:
        payload = body
    conn.request(method, path, body=payload, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    reply = Reply(resp.status, {k.lower(): v for k, v in resp.getheaders()}, data)
    conn.close()
    return reply


INDEX = "<!doctype html><html><head><title>t</title></head><body>hi</body></html>"


@dataclass
class Live:
    """Handle on a running test server."""

    server: AppServer
    backend: FakeBackend
    dist: Path
    token: str
    port: int

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def post_headers(self) -> dict[str, str]:
        return {"Origin": self.origin, "X-Todoimpl-Token": self.token, "Content-Type": "application/json"}


def post(live: Live, action: str, body: Any = None, **hdr: str) -> Reply:
    """POST an action with good credentials; a header value of "-" drops that header."""
    headers = {**live.post_headers(), **hdr}
    headers = {k: v for k, v in headers.items() if v != "-"}
    path = f"/api/task/{live.backend.task_id}/{action}"
    return call(live.port, "POST", path, body if body is not None else {}, headers)
