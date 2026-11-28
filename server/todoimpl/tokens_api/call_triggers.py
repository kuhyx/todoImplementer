"""Class of the tool result that triggered an API call (the per-call inspector).

A call is triggered by the tool results in the user message before it: the
results of the previous call's tool uses. When one call ran several tools, the
one with the biggest result names the class (an image outweighs any text).
"""

from __future__ import annotations

import re
from typing import NamedTuple

PROMPT = "prompt"
OTHER = "other"
CLASSES = ("prompt", "test", "read", "screenshot", "wait", "edit", "subagent", OTHER)

_TEST = re.compile(
    r"\b(?:pytest|vitest)\b|\bflutter\s+test\b|\bmake\s+(?:test|fast)\b|\bgo\s+test\b|\bcargo\s+test\b"
)
# A command that is only waiting: it starts with the wait, or holds a watcher.
_WAIT_START = re.compile(r"^\s*(?:sleep|until|while)\b|\btail\b.*--pid|\binotifywait\b|\bgh\s+run\s+watch\b")
_WAIT_ANY = re.compile(r"\bsleep\b")
_WAIT_TOOLS = frozenset({"Monitor", "TaskOutput", "ScheduleWakeup"})
_EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})
_READ_TOOLS = frozenset({"Read", "Grep", "Glob"})
_SUBAGENT_TOOLS = frozenset({"Agent", "Task"})


class Call(NamedTuple):
    """One stored tool call, as far as classifying its result needs."""

    name: str
    family: str
    target: str
    images: int
    result_tokens: int


def _bash(command: str) -> str:
    """Class of a Bash command."""
    if _WAIT_START.search(command):
        return "wait"
    if _TEST.search(command):
        return "test"
    return "wait" if _WAIT_ANY.search(command) else OTHER


def classify(call: Call) -> str:
    """Return the trigger class of one tool call's result."""
    name = call.name
    if call.images or call.family == "Read:image":
        return "screenshot"
    if name == "Bash":
        return _bash(f"{call.target} {call.family}")
    if name in _WAIT_TOOLS or name.endswith("__await_reply"):
        return "wait"
    if name in _EDIT_TOOLS:
        return "edit"
    if name in _READ_TOOLS:
        return "read"
    return "subagent" if name in _SUBAGENT_TOOLS else OTHER


def trigger(calls: list[Call]) -> str:
    """Class of the call whose result was biggest; :data:`OTHER` with no calls."""
    if not calls:
        return OTHER
    return classify(max(calls, key=lambda call: call.result_tokens))
