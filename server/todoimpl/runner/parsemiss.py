"""A Claude question no parser rule reads files a board error record, so the miss becomes a ticket (T2527).

A turn that ends on `Q:` with a `❓` line neither question pattern of `parsing.py` matches shows the
full-text fallback card meanwhile (`board/askfallback.py`); the record (`stall/report.py`, signature
`question-parse-miss`) is one todoImplementer ticket by the errors loop; a later miss raises its count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.stall import report

from .parsing import QUESTION, QUESTION_JOINED

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

SIGNATURE = "question-parse-miss"
KIND = "parse.miss"
MESSAGE = "a Claude question had a ❓ line no parser rule reads, so it showed as one free card"
MARK = "❓"
MAX_DETAIL = 200


def _unread(text: str) -> str | None:
    """Return the first ❓ line no question pattern matches, None when every one parses."""
    for line in text.splitlines():
        if line.lstrip().startswith(MARK) and not (QUESTION.match(line) or QUESTION_JOINED.match(line)):
            return line.strip()
    return None


def check(driver: Driver, res: TurnResult, stage: str) -> bool:  # noqa: ARG001 - the turn-hook signature
    """File the miss of a finished `Q:` turn; always False: the session is not resumed for it."""
    if res.tag == "Q" and (line := _unread(res.text)) is not None:
        detail = f"card {driver.state.task_id}: {line}"[:MAX_DETAIL]
        report.file(SIGNATURE, detail, driver.ctx.now(), kind=KIND, message=MESSAGE)
    return False
