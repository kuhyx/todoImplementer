"""The Haiku triage of one repo-less note (`runner/oneshot.py`, same call as the merge classifier)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import run_root
from todoimpl.runner import oneshot
from todoimpl.runner.claude import DENY_ALWAYS, DENY_READONLY, model_for

from .label import ALL_REPOS, EXISTING_REPO, LABELS, NEW_REPO, Verdict

if TYPE_CHECKING:
    from pathlib import Path

TIMEOUT_S = 50.0  # under the 60 s per-action cap
BODY_CHARS = 1500
PATH = re.compile(r"[\w.][\w./-]*")  # never starts with a dash, `..` is refused in parse
NAME = re.compile(r"[a-z0-9][a-z0-9-]{1,38}[a-z0-9]")
PROMPT = """override
You label one todo note that has no repo yet. Labels:
- new_repo: it asks to build a NEW app, tool, site, game or library (nothing exists for it yet). Give "name",
  a short kebab-case repo name (letters, digits, hyphens).
- existing_repo: it clearly belongs to ONE of kuhy's repos listed below. Give "repo" exactly as listed.
- all_repos: it asks for one change across many or all of kuhy's repos. Give "token", the most specific short
  literal that appears in the files of the repos the change applies to (take it from the file names below when
  they fit; never a common word like version, test or build), and "path", the directory it is in (such as
  .github); omit both when every repo applies.
- research: it is mainly URLs or articles to read, study and turn into suggested actions.
- manual: not code: an errand, a message to send, a link to read for fun, a puzzle, a question to think about.
When unsure between manual and anything else, choose manual.

kuhy's repos: {repos}
File names under .github/workflows in those repos, with how many repos have each: {files}

Note title: {title}
Note text: {body}

Reply with ONLY a JSON object
{{"label": "...", "reason": "one line", "repo": "...", "name": "...", "token": "...", "path": "..."}};
omit the fields the label does not use.
"""


class ClassifyError(Exception):
    """The classifier call or its answer was unusable."""


def build_prompt(title: str, body: str, repos: list[str], files: list[str] | None = None) -> str:
    """Return the prompt for one note; the body is cut so a pasted article never costs more than a line."""
    text = " ".join(body.split())[:BODY_CHARS] or "(none)"
    return PROMPT.format(
        repos=", ".join(repos) or "(none)", files=", ".join(files or []) or "(none)", title=title, body=text
    )


def claude_classifier(prompt: str, root: Path | None = None) -> str:
    """Run the narrow, read-only Haiku one-shot; return its text."""
    return oneshot.run(
        prompt, model=model_for("classify"), kind="triage", root=root or run_root(), timeout=TIMEOUT_S,
        error=ClassifyError, deny=DENY_ALWAYS + DENY_READONLY,
    )  # fmt: skip


def _text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse(text: str, repos: list[str]) -> Verdict:
    """Pull the JSON object out of the model text and validate it against kuhy's repo list.

    A label the note cannot act on (an unknown repo, a bad name) becomes `manual` with the reason, so the card
    stays Yours instead of the call being repeated; text that is no object at all raises `ClassifyError`.
    """
    start, end = text.find("{"), text.rfind("}")
    try:
        data: Any = json.loads(text[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("label") not in LABELS:
        msg = f"answer is not a JSON object with a label: {text[:200]!r}"
        raise ClassifyError(msg)
    label, reason = str(data["label"]), (_text(data, "reason") or "").splitlines()[:1]
    why = reason[0] if reason else ""
    if label == EXISTING_REPO:
        repo = _text(data, "repo")
        found = next((r for r in repos if repo and r.lower() == repo.lower()), None)
        return Verdict(label, why, repo=found) if found else Verdict("manual", f"unknown repo {repo}: {why}")
    if label == NEW_REPO:
        name = _text(data, "name")
        return (
            Verdict(label, why, name=name)
            if name and NAME.fullmatch(name)
            else Verdict("manual", f"bad repo name {name}: {why}")
        )
    if label == ALL_REPOS:
        path = _text(data, "path")
        ok = path is not None and PATH.fullmatch(path) and ".." not in path
        return Verdict(label, why, token=_text(data, "token"), path=path if ok else None)
    return Verdict(label, why)
