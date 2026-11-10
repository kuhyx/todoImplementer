"""The Haiku classifier: groups open notes of one kind of work. One-shot `claude -p`, role `classify`."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.runner.claude import DENY_ALWAYS, DENY_READONLY, claude_bin, model_for

if TYPE_CHECKING:
    from todoimpl.service.cards import CardTask

TIMEOUT_S = 50.0  # under the 60 s per-action cap
BODY_CHARS = 300
MIN_MEMBERS = 2
PROMPT = """override
You group todo notes that are the same kind of work: many notes that ask for the same change in different
repos or apps, or duplicate notes for one thing. Do not group notes that merely share a topic.
Notes, one per line as `id | repo | title | first characters of the text`:
{notes}

Reply with ONLY a JSON object {{"groups": [{{"ids": [...], "title": "...", "reason": "..."}}]}}.
Each group has at least 2 ids taken from the list, a note appears in at most one group, "title" is the
title of the one combined note, "reason" is one line on why they belong together.
No group is fine: {{"groups": []}}.
"""


class ClassifyError(Exception):
    """The classifier call or its answer was unusable."""


@dataclass(frozen=True)
class Group:
    """A validated proposal: card ids (distinct, >= 2), the combined title and the reason."""

    ids: tuple[str, ...]
    title: str
    reason: str


def build_prompt(cards: list[CardTask]) -> str:
    """Return the prompt: id, repo, title and the first 300 characters of each body (one line each)."""
    rows = [
        f"{card.id} | {card.repo} | {card.title} | {' '.join(card.body.split())[:BODY_CHARS]}"
        for card in cards
    ]
    return PROMPT.format(notes="\n".join(rows))


def claude_classifier(prompt: str) -> str:
    """Run `claude -p --model haiku --output-format json --strict-mcp-config` (read-only); return its text."""
    argv = [
        claude_bin(),
        "-p",
        "--model",
        model_for("classify"),
        "--output-format",
        "json",
        "--strict-mcp-config",
        "--disallowedTools",
        ",".join(DENY_ALWAYS + DENY_READONLY),
    ]
    env = {**os.environ, "CLAUDE_AUTO_CONTINUE": "0"}  # handoff hooks must not spawn untracked sessions
    try:
        proc = subprocess.run(  # noqa: S603
            argv, input=prompt, capture_output=True, text=True, env=env, timeout=TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"claude timed out after {TIMEOUT_S:g}s"
        raise ClassifyError(msg) from exc
    except OSError as exc:
        msg = f"cannot run claude: {exc}"
        raise ClassifyError(msg) from exc
    if proc.returncode != 0:
        msg = f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-200:]}"
        raise ClassifyError(msg)
    try:
        envelope = json.loads(proc.stdout)
    except ValueError as exc:
        msg = f"claude printed non-JSON: {proc.stdout[:200]!r}"
        raise ClassifyError(msg) from exc
    answer = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(answer, str) or envelope.get("is_error"):
        msg = f"claude returned no text: {proc.stdout[:200]!r}"
        raise ClassifyError(msg)
    return answer


def _group(raw: Any, valid: set[str], used: set[str]) -> Group | None:  # noqa: ANN401 - parsed JSON
    """One proposed group, or None when any rule is broken (ids known and unused, >= 2 distinct, texts)."""
    if not isinstance(raw, dict):
        return None
    ids, title, reason = raw.get("ids"), raw.get("title"), raw.get("reason")
    if not (isinstance(ids, list) and isinstance(title, str) and isinstance(reason, str)):
        return None
    if not all(isinstance(i, str) and i in valid and i not in used for i in ids):
        return None
    distinct = tuple(dict.fromkeys(ids))
    line = next(iter(reason.strip().splitlines()), "").strip()
    if len(distinct) < MIN_MEMBERS or not title.strip() or not line:
        return None
    return Group(distinct, title.strip(), line)


def parse_groups(text: str, valid: set[str]) -> list[Group]:
    """Pull the JSON object out of the model text and keep only valid groups (a note in at most one)."""
    start, end = text.find("{"), text.rfind("}")
    try:
        data: Any = json.loads(text[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        msg = f"answer is not a JSON object with groups: {text[:200]!r}"
        raise ClassifyError(msg)
    found: list[Group] = []
    used: set[str] = set()
    for raw in data["groups"]:
        group = _group(raw, valid, used)
        if group is not None:
            found.append(group)
            used.update(group.ids)
    return found
