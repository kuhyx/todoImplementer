"""Incremental reader for `claude -p --output-format stream-json`: activity, session, cost, result, tag."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .ctxcap import context_of
from .limits import LimitInfo, blocking, parse_event

if TYPE_CHECKING:
    from collections.abc import Callable

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


@dataclass(frozen=True)
class Denial:
    """A tool call claude was refused; `hook` = a PreToolUse hook said no (an allow rule cannot lift that)."""

    tool_name: str
    tool_use_id: str
    tool_input: dict[str, Any]
    hook: bool
    message: str
    terminal: bool  # no tool call succeeded afterwards: claude stopped on it
    safety: bool = False  # Claude Code's own "sensitive file" check: bypass mode does not lift it


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
    denials: list[Denial] = field(default_factory=list)
    model_usage: dict[str, Any] = field(default_factory=dict)  # the result event's `modelUsage`
    live_usd: float = 0.0  # a credit turn's cost so far, estimated from its usage (list price)
    context_tokens: int = 0  # the main thread's context at its latest assistant message (`ctxcap`)


def parse_tag(text: str) -> str | None:
    """Return the letter of the last status-tag line (D, R, Q, A or C); `N:` notes are not tags."""
    tag = None
    for found in TAG_LINE.finditer(text):
        tag = found.group(3) or LONG[found.group(1) or found.group(2)]
    return tag


def last_tag_match(text: str) -> re.Match[str] | None:
    """Return the match of the last status-tag line in `text`, None without one."""
    found = None
    for match in TAG_LINE.finditer(text):
        found = match
    return found


def tag_letter(match: re.Match[str]) -> str:
    """Return the status letter (D/R/Q/A/C) a TAG_LINE match stands for."""
    return match.group(3) or LONG[match.group(1) or match.group(2)]


def last_tag_line(text: str) -> tuple[str, str] | None:
    """Return (letter, text after the colon) of the last status-tag line, None without one."""
    found = last_tag_match(text)
    if found is None:
        return None
    line_end = text.find("\n", found.end())
    rest = text[found.end() : None if line_end < 0 else line_end]
    return tag_letter(found), rest.strip(" \t*_`")


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
        self._seq = 0
        self._last_ok = 0
        self._errors: dict[str, tuple[int, str]] = {}
        self._safety: set[str] = set()
        self.on_context: Callable[[int], None] | None = None  # told each main-thread context (the cap brake)

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
            self._context(obj)
            return self._assistant(obj.get("message"))
        if kind == "user":
            self._tool_results(obj.get("message"))
            return []
        if kind == "result":
            return [self._result(obj)]
        if kind == "rate_limit_event":
            return self._limit(obj)
        return self._system(obj) if kind == "system" else []

    def _context(self, obj: dict[str, Any]) -> None:
        tokens = context_of(obj)
        if tokens is not None:
            self.result.context_tokens = tokens
            if self.on_context is not None:
                self.on_context(tokens)

    def _system(self, obj: dict[str, Any]) -> list[Activity]:
        subtype = obj.get("subtype")
        if subtype == "permission_denied" and obj.get("decision_reason_type") == "safetyCheck":
            self._safety.add(str(obj.get("tool_use_id")))
        if subtype == "init":
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

    def _tool_results(self, message: object) -> None:
        """Remember each failed tool_result (order and text) and the order of the last successful one."""
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            self._seq += 1
            if block.get("is_error") is not True:
                self._last_ok = self._seq
                continue
            body = block.get("content")
            text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
            self._errors[str(block.get("tool_use_id"))] = (self._seq, text[:MAX_TEXT])

    def _denials(self, raw: object) -> list[Denial]:
        out: list[Denial] = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("tool_name"), str):
                continue
            uid = str(item.get("tool_use_id"))
            seq, text = self._errors.get(uid, (self._seq + 1, ""))
            given = item.get("tool_input")
            out.append(
                Denial(
                    item["tool_name"], uid, given if isinstance(given, dict) else {},
                    text.startswith("PreToolUse:") and "hook error" in text[:120], text, seq > self._last_ok,
                    uid in self._safety,
                )
            )  # fmt: skip
        return out

    def _result(self, obj: dict[str, Any]) -> Activity:
        res = self.result
        text, errors = obj.get("result"), obj.get("errors")
        said = [e for e in errors if isinstance(e, str)] if isinstance(errors, list) else []
        res.text = text if isinstance(text, str) else "; ".join(said)  # an error result has `errors` only
        cost = obj.get("total_cost_usd")
        res.cost_usd = float(cost) if isinstance(cost, int | float) else 0.0
        usage = obj.get("modelUsage")
        res.model_usage = usage if isinstance(usage, dict) else {}
        turns = obj.get("num_turns")
        res.num_turns = turns if isinstance(turns, int) else 0
        res.is_error = obj.get("is_error") is True
        res.tag = parse_tag(res.text)
        res.finished = True
        res.denials = self._denials(obj.get("permission_denials"))
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
