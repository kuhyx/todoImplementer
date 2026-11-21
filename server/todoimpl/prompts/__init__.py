"""Stage prompts for the Claude sessions the runner starts: `build(stage, ctx)`."""

from __future__ import annotations

from .context import PromptContext
from .kind import Kind, detect_kind
from .proof import live_proof
from .texts import STAGES, build

STAGES["live_proof"] = live_proof  # here, not in texts.py: proof.py builds on texts

__all__ = ["STAGES", "Kind", "PromptContext", "build", "detect_kind"]
