"""Which model kuhy pins a card to: the picker's choices and the note that names one (no LLM, plain regex).

A note is a model command only when the whole note is one: an optional verb phrase ("run it on", "rerun on",
"use", "switch to"), then a known model ("claude fable 5.2", "opus", "sonnet 5.5"), or `default`. Anything
else (another version, more words, "use sonnet for the classifier") is a normal note. The pin lives in
`state.extra.model_pin` and wins over the role, tier and escalation models until kuhy names another
or `default`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Model:
    """One model the picker offers: its CLI id, family word, version and short label."""

    id: str
    family: str
    version: str
    label: str


MODELS: Final = (
    Model("claude-fable-5-2", "fable", "5.2", "Fable 5.2"),
    Model("claude-opus-5-5", "opus", "5.5", "Opus 5.5"),
    Model("claude-sonnet-5-5", "sonnet", "5.5", "Sonnet 5.5"),
    Model("claude-haiku-5-5", "haiku", "5.5", "Haiku 5.5"),
)
DEFAULT: Final = "default"  # drops the pin: the role, tier and escalation rules pick again
PIN: Final = "model_pin"  # state.extra key
IDS: Final = (*(m.id for m in MODELS), DEFAULT)

_VERB = r"(?:(?:please\s+)?(?:go\s+)?(?:back\s+)?(?:re\s*run|run|re\s*do|redo|do|use|switch|try|go)?"
_VERB += r"(?:\s+(?:it|this|that|the\s+task|the\s+card|again))*\s*)?"
_PREP = r"(?:(?:back\s+)?(?:on|with|to|using|in)\s+)?"
_NAME = r"(?:claude\s+)?(?P<family>fable|opus|sonnet|haiku)(?:\s+(?P<version>\d+(?:[.\s]\d+)?))?"
_DEFAULT = r"(?P<default>(?:the\s+)?default)"
_TAIL = r"(?:\s+model)?(?:\s+(?:again|instead|please|now))*"
COMMAND: Final = re.compile(rf"{_VERB}{_PREP}(?:{_NAME}|{_DEFAULT}){_TAIL}")


def _norm(text: str) -> str:
    """Lower case, hyphens and underscores as spaces, single spaces, no closing punctuation."""
    flat = re.sub(r"[-_\s]+", " ", text.lower()).strip()
    return flat.rstrip(".!? ").strip()


def _known(family: str, version: str | None) -> str | None:
    """Return the id of `family` when the version (if any) is its own: `5.2`, `5 2` or the major `5`."""
    found = next(m for m in MODELS if m.family == family)
    if version is None:
        return found.id
    given = version.replace(" ", ".")
    return found.id if given in {found.version, found.version.split(".")[0]} else None


def parse(text: str) -> str | None:
    """Return the model id the note names, `default`, or None when the note is not a model command."""
    match = COMMAND.fullmatch(_norm(text))
    if match is None:
        return None
    if match.group("default"):
        return DEFAULT
    return _known(match.group("family"), match.group("version"))


def label(model_id: str) -> str:
    """Return the short label of an id the picker knows, else the id itself."""
    return next((m.label for m in MODELS if m.id == model_id), model_id)


def choices() -> list[dict[str, str]]:
    """Return the picker's choices (action.schema `choices`): every model, then `default`."""
    return [{"id": m.id, "label": m.label} for m in MODELS] + [{"id": DEFAULT, "label": "Default"}]
