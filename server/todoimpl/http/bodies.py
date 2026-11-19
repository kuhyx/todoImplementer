"""Request-body checks mirroring contracts/requests.schema.json (stdlib only, no jsonschema at runtime)."""

from __future__ import annotations

import json
import re
from typing import Any

from todoimpl import modelpick
from todoimpl.newtask import noteimages

QUESTION_ID = re.compile(r"Q[0-9]+")
MAX_TEXT = 20000
ACTIONS = (
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
    "wont",
    "done-manually",
    "model",
)


def parse(raw: bytes) -> dict[str, Any] | str:
    """Return the JSON object in `raw` (empty means {}), or why it is not one."""
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        return "body is not valid JSON"
    return body if isinstance(body, dict) else "body must be a JSON object"


def _only(body: dict[str, Any], key: str) -> str | None:
    return None if set(body) == {key} else f"body must be exactly {{{key}}}"


def _answers(body: dict[str, Any]) -> str | None:
    if (bad := _only(body, "answers")) is not None:
        return bad
    answers = body["answers"]
    if not isinstance(answers, dict) or not answers:
        return "answers must be a non-empty object"
    ok = all(QUESTION_ID.fullmatch(k) and isinstance(v, str) and v for k, v in answers.items())
    return None if ok else "answers must map Q<n> to non-empty text"


def _text(body: dict[str, Any]) -> str | None:
    if "text" not in body or not set(body) <= {"text", "images"}:
        return "body must be {text, images?}"
    text = body["text"]
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
        return f"text must be 1..{MAX_TEXT} characters"
    try:
        images(body)
    except noteimages.ImageError as exc:
        return str(exc)
    return None


def images(body: dict[str, Any]) -> tuple[noteimages.Ref, ...]:
    """Return a send body's `[Image #N]` refs in order; raise ImageError on a bad one."""
    return noteimages.parse(body.get("images", []))


def _lesson(body: dict[str, Any]) -> str | None:
    if (bad := _only(body, "lesson_id")) is not None:
        return bad
    lesson = body["lesson_id"]
    return None if isinstance(lesson, str) and lesson else "lesson_id must be non-empty text"


def _start(body: dict[str, Any]) -> str | None:
    if not body:
        return None
    if (bad := _only(body, "auto_ship")) is not None:
        return bad
    return None if isinstance(body["auto_ship"], bool) else "auto_ship must be true or false"


def _model(body: dict[str, Any]) -> str | None:
    if (bad := _only(body, "model")) is not None:
        return bad
    return None if body["model"] in modelpick.IDS else f"model must be one of {', '.join(modelpick.IDS)}"


def check(action: str, body: dict[str, Any]) -> str | None:
    """Return what is wrong with the body for this action, or None when it is valid."""
    if action == "start":
        return _start(body)
    if action == "spec-answers":
        return _answers(body)
    if action == "send":
        return _text(body)
    if action == "lesson-approve":
        return _lesson(body)
    if action == "model":
        return _model(body)
    return None if not body else "body must be empty"
