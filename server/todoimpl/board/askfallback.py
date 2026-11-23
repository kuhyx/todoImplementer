"""The one question card of a Claude question no parser rule splits into cards: its full text (T2525).

The Needs text under the card title is a one-line summary clipped at 200 characters (`ask.py`); the
Questions tab shows this card instead, so kuhy reads the whole question before he answers it.
"""

from __future__ import annotations

from typing import Any

from todoimpl.runner.parsing import RECOMMENDATION
from todoimpl.runner.stream import last_tag_match

MARK = "❓"
VARIATION = "\ufe0f"  # the emoji form of ❓
TITLE = "Claude asks"


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _marked(lines: list[str]) -> tuple[str, str] | None:
    """Body from the first ❓ line on (the mark dropped) and the first ➡️ line's text, None without a ❓."""
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith(MARK)), None)
    if start is None:
        return None
    body: list[str] = []
    recommendation = ""
    for line in lines[start:]:
        if (arrow := RECOMMENDATION.match(line)) is not None:
            recommendation = recommendation or arrow.group(1)
        else:
            body.append(line.strip())
    body[0] = body[0].removeprefix(MARK).lstrip(VARIATION).strip()
    return "\n".join(body).strip(), recommendation


def _unmarked(before: str, after: str) -> str:
    """Return the text after the tag, else the last paragraph before it."""
    if after.strip():
        return after.strip()
    found = _paragraphs(before)
    return found[-1] if found else ""


def fallback(reply: str) -> dict[str, Any] | None:
    """Return the one full-text card of the reply's question, None when the reply asks nothing."""
    tag = last_tag_match(reply)
    before, after = (reply, "") if tag is None else (reply[: tag.start()], reply[tag.end() :])
    marked = _marked(before.splitlines())
    body, recommendation = marked if marked is not None else (_unmarked(before, after), "")
    if not body:
        return None
    return {"id": "Q1", "title": TITLE, "body": body, "recommendation": recommendation, "answer": None}
