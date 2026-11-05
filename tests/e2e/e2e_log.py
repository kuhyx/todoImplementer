"""Step logging, the two ways a step stops early, and the failure artefacts."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import NoReturn

from e2e_world import SCRATCH, State

FLOW = "F1"
TOTAL = 6


class FailError(Exception):
    """The step ran and the expectation did not hold."""


class PendingError(Exception):
    """The step is not finished yet (a slow stage); run the same step again."""


def fail(text: str) -> NoReturn:
    """Stop the step as failed with this message."""
    raise FailError(text)


def say(state: State, step: int, text: str) -> None:
    """Print and record one numbered line before the work it names runs."""
    line = f"{FLOW} step {step}/{TOTAL}: {text}"
    print(line, flush=True)
    log = state.path / "artifacts" / "steps.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as out:
        out.write(line + "\n")


def save_artifacts(state: State, tag: str) -> Path:
    """Copy logs, board snapshots and fake-claude calls to the scratch area; return that folder."""
    dest = SCRATCH / f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}"
    shutil.copytree(state.path / "artifacts", dest, dirs_exist_ok=True)
    for calls in (state.path / "fake").glob("runs/*/calls.jsonl"):
        shutil.copy(calls, dest / f"claude-calls-{calls.parent.name}.jsonl")
    return dest
