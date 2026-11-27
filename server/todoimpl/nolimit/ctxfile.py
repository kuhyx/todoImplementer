"""Where the no-limit runner leaves a card's next-turn context: a leaf, so the prompt can name it (T2600).

`prompts.nolimitctx` imports this, never `nolimit.context`: that one runs capped steps through
`runner.checks`, which imports the prompts: an import cycle that broke `python -m todoimpl.nolimit.tick`.
"""

from __future__ import annotations

from pathlib import Path

FILE = "nolimit-context.md"


def path(run_dir: Path) -> Path:
    """Return the card's context file."""
    return run_dir / FILE
