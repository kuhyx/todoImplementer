"""Incremental reader for `claude -p --output-format stream-json`: activity, session, cost, result, tag."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .limits import LimitInfo, blocking, parse_event

# Same accepted forms as ~/.claude/hooks/status_tag_stop.py (long forms still pass there).
TAG_LINE = re.compile(
    r"^[\s>*_#-]*(?:(CONTINUING) in new session"
    r"|(DONE|RUNNING|QUESTION|NEEDS ACTION)[*_]*\s*|([DRQAC])[*_]*):",
    re.MULTILINE,
)
LONG = {"DONE": "D", "RUNNING": "R", "QUESTION": "Q", "NEEDS ACTION": "A", "CONTINUING": "C"}
INPUT_KEYS = ("command", "file_path", "path", "pattern", "url", "skill", "description", "prompt", "query")
MAX_TEXT = 2000
MAX_INPUT = 160


@dataclass(frozen=True)
class Activity:
    """One live-feed line: kind is text|tool|result|error|system, tool names the tool for kind=tool."""

    kind: str
    text: str
    tool: str | None = None


@dataclass
class TurnResult:
    """What one claude process reported; `finished` is False when no result event arrived."""

    session_id: str | None = None
    cost_usd: float = 0.0
    text: str = ""
    tag: str | None = None
    is_error: bool = False
    num_turns: int = 0
    finished: bool = False
    limit: LimitInfo | None = None


def parse_tag(text: str) -> str | None:
    """Return the letter of the last status-tag line (D, R, Q, A or C); `N:` notes are not tags."""
    tag = None
    for found in TAG_LINE.finditer(text):
        tag = found.group(3) or LONG[found.group(1) or found.group(2)]
    return tag


def last_tag_line(text: str) -> tuple[str, str] | None:
    """Return (letter, text after the colon) of the last status-tag line, None without one."""
    found = None
    for match in TAG_LINE.finditer(text):
        found = match
    if found is None:
        return None
    letter = found.group(3) or LONG[found.group(1) or found.group(2)]
    line_end = text.find("\n", found.end())
    rest = text[found.end() : None if line_end < 0 else line_end]
    return letter, rest.strip(" \t*_`")


def state_tag(tag: str | None) -> str | None:
    """state.json allows Q/A/R/D only; a `C:` handoff is still running work."""
    return "R" if tag == "C" else tag


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def short_input(value: object) -> str:  # noqa: D103
    if isinstance(value, dict):
        for key in INPUT_KEYS:
            field = value.get(key)
            if isinstance(field, str) and field:
                return _clip(" ".join(field.split()), MAX_INPUT)
    return _clip(" ".join(json.dumps(value, ensure_ascii=False, sort_keys=True).split()), MAX_INPUT)


class StreamParser:
    """Feed it stdout lines; read `result` once the process exits."""

    def __init__(self) -> None:  # noqa: D107
        self.result = TurnResult()

    def feed(self, line: str) -> list[Activity]:  # noqa: PLR0911 - one return per event type
        """Parse one line; torn, non-JSON and uninteresting events (hooks, thinking) yield nothing."""
        try:
            obj = json.loads(line)
        except ValueError:
            return []
        if not isinstance(obj, dict):
            return []
        sid = obj.get("session_id")
        if isinstance(sid, str) and sid:
            self.result.session_id = sid
        kind = obj.get("type")
        if kind == "assistant":
            return self._assistant(obj.get("message"))
        if kind == "result":
            return [self._result(obj)]
        if kind == "rate_limit_event":
            return self._limit(obj)
        if kind == "system" and obj.get("subtype") == "init":
            return [Activity("system", f"session started ({obj.get('model')})")]
        return []

    @staticmethod
    def _assistant(message: object) -> list[Activity]:
        content = message.get("content") if isinstance(message, dict) else None
        out: list[Activity] = []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                out.append(Activity("tool", short_input(block.get("input")), str(block.get("name"))))
            elif block.get("type") == "text" and str(block.get("text", "")).strip():
                out.append(Activity("text", _clip(str(block["text"]).strip(), MAX_TEXT)))
        return out

    def _result(self, obj: dict[str, Any]) -> Activity:
        res = self.result
        text = obj.get("result")
        res.text = text if isinstance(text, str) else ""
        cost = obj.get("total_cost_usd")
        res.cost_usd = float(cost) if isinstance(cost, int | float) else 0.0
        turns = obj.get("num_turns")
        res.num_turns = turns if isinstance(turns, int) else 0
        res.is_error = obj.get("is_error") is True
        res.tag = parse_tag(res.text)
        res.finished = True
        shown = _clip(res.text.strip(), MAX_TEXT) or f"turn ended ({obj.get('subtype')})"
        return Activity("error" if res.is_error else "result", shown)

    def _limit(self, obj: dict[str, Any]) -> list[Activity]:
        info = parse_event(obj)
        if info is None:
            return []
        self.result.limit = info
        if not blocking(info):
            return []
        return [Activity("error", f"plan limit reached; runs pause until {info.resets_at}")]
