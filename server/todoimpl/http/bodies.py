"""Request-body checks mirroring contracts/requests.schema.json (stdlib only, no jsonschema at runtime)."""

from __future__ import annotations

import re
from typing import Any

QUESTION_ID = re.compile(r"Q[0-9]+")
MAX_TEXT = 20000
ACTIONS = ("start", "spec-answers", "spec-ok", "send", "ship", "cancel", "credits", "lesson-approve")


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
    if (bad := _only(body, "text")) is not None:
        return bad
    text = body["text"]
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
        return f"text must be 1..{MAX_TEXT} characters"
    return None


def _lesson(body: dict[str, Any]) -> str | None:
    if (bad := _only(body, "lesson_id")) is not None:
        return bad
    lesson = body["lesson_id"]
    return None if isinstance(lesson, str) and lesson else "lesson_id must be non-empty text"


def check(action: str, body: dict[str, Any]) -> str | None:
    """Return what is wrong with the body for this action, or None when it is valid."""
    if action == "spec-answers":
        return _answers(body)
    if action == "send":
        return _text(body)
    if action == "lesson-approve":
        return _lesson(body)
    return None if not body else "body must be empty"
