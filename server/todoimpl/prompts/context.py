"""Everything a stage prompt may mention, as one frozen value the runner fills per call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptContext:
    """Inputs for `build`. Optional fields default to empty so early stages stay short."""

    title: str
    body: str
    repo: str
    worktree: Path
    run_dir: Path
    done_check: str | None = None
    plan_md: str = ""
    spec_answers: tuple[tuple[str, str], ...] = ()  # (question title, kuhy's answer)
    notes: tuple[str, ...] = ()  # kuhy's "Send to Claude" messages, oldest first
    failure_tail: str = ""  # tail of the failed live_check / checks output
    handoff: str = ""  # summary carried into a fresh session after idle
    phone: dict[str, Any] | None = None  # phone_ready.json of a run whose phone is attached now
