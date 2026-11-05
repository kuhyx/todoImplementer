"""Stage prompts for the Claude sessions the runner starts: `build(stage, ctx)`."""

from __future__ import annotations

from .context import PromptContext
from .kind import Kind, detect_kind
from .texts import STAGES, build

__all__ = ["STAGES", "Kind", "PromptContext", "build", "detect_kind"]
