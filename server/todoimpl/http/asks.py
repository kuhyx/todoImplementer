"""POST /api/task/<id>/ask/<verb>: the buttons of an ask block (contracts/requests.schema.json `ask_*`)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from . import bodies
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

POST_PATH = re.compile(
    r"/api/task/([A-Za-z0-9]{8}-[0-9]+)/ask/(answer|take-recommended|run|undo|approve|reject)"
)
ASK_ID = re.compile(r"[a-z][a-z0-9_]{0,15}")


@runtime_checkable
class AskApi(Protocol):
    """What the routes need from the ask service; refusals are BackendError."""

    def answer(self, id8: str, ask_id: str, option: str) -> None:
        """Click an option."""
        ...

    def take_recommended(self, id8: str) -> None:
        """Take every open recommended option."""
        ...

    def run_command(self, id8: str, ask_id: str, *, add: bool) -> dict[str, Any]:
        """Run a command ask."""
        ...

    def undo(self, id8: str, ask_id: str) -> None:
        """Reopen an auto-adopted choice."""
        ...

    def verdict(self, id8: str, ask_id: str, *, approve: bool) -> None:
        """Approve or reject a screenshot."""
        ...


def _check(verb: str, body: dict[str, Any]) -> str | None:
    """Mirror of the request schemas: the exact keys each verb takes."""
    keys = {"take-recommended": set(), "answer": {"ask", "option"}, "run": {"ask", "add"}}.get(verb, {"ask"})
    required = keys - {"add"}
    if not required <= set(body) <= keys:
        return f"body must be exactly {sorted(keys)}"
    if "ask" in keys and not (isinstance(body["ask"], str) and ASK_ID.fullmatch(body["ask"])):
        return "ask must be an ask id"
    if verb == "answer" and not (
        isinstance(body["option"], str) and 0 < len(body["option"]) <= bodies.MAX_TEXT
    ):
        return "option must be text"
    if "add" in body and not isinstance(body["add"], bool):
        return "add must be true or false"
    return None


def handle_post(api: AskApi, found: re.Match[str], raw: bytes) -> Reply:
    """Run the click named by the path and answer {ok: true, result?}."""
    body = bodies.parse(raw)
    if isinstance(body, str):
        return error_reply("bad_request", body)
    id8, verb = found.groups()
    if (problem := _check(verb, body)) is not None:
        return error_reply("bad_request", problem)
    result: dict[str, Any] | None = None
    clicks: dict[str, Callable[[], None]] = {
        "answer": lambda: api.answer(id8, body["ask"], body["option"]),
        "take-recommended": lambda: api.take_recommended(id8),
        "undo": lambda: api.undo(id8, body["ask"]),
        "approve": lambda: api.verdict(id8, body["ask"], approve=True),
        "reject": lambda: api.verdict(id8, body["ask"], approve=False),
    }
    if verb == "run":
        result = api.run_command(id8, body["ask"], add=body.get("add") is True)
    else:
        clicks[verb]()
    return json_reply({"ok": True, **({"result": result} if result is not None else {})})


def api_of(backend: object) -> AskApi | None:
    """Return the ask service the backend carries (`ask_service`), None when it has none."""
    api = getattr(backend, "ask_service", None)
    return api if isinstance(api, AskApi) else None
