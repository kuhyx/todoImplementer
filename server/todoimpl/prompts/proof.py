"""The proof round's prompt: check only the ticked parts no passed live row names (T2467)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import standing, texts

if TYPE_CHECKING:
    from .context import PromptContext

NOW = (
    "A check you can run now is never `after ship` and never `not rerun`: a busy build slot only queues it. "
    "For a part that asks for a command to finish under 60 s, run that command timed and write the seconds. "
    "`[~]` closes no part: use it only for what cannot be seen now at all (kuhy's phone away, a human sense)."
)
ONLY = (
    "Check only their criteria now, for real, from {wt}: start the changed thing, run the command, look at "
    "the result. Do not change code. Do not check the other parts again."
)
ROWS = (
    "Write only their rows to {run_dir}/live_check.md, one line per criterion (the board keeps the other "
    "rows):"
)


def live_proof(ctx: PromptContext) -> str:
    """Ask for the rows of the named parts alone; the board merges them into the stored checklist."""
    seeded = (
        [f"Handoff from the implementer (you are a fresh session):\n{ctx.handoff}"] if ctx.handoff else []
    )
    return "\n".join(
        [
            texts.OVERRIDE,
            "Ship is held: these ticked parts have no passed live row, so they would stay open:",
            ctx.failure_tail[-texts.TAIL_CHARS :],
            texts.item(ctx),
            *seeded,
            texts.plan_text(ctx),
            ONLY.format(wt=ctx.worktree),
            NOW,
            ROWS.format(run_dir=ctx.run_dir),
            "- [x] C3 [<part key>]: what I did -> what I saw   (`- [ ]` if it failed: a fix turn gets it)",
            standing.WAITS,
            "Stop what you started. End with `D:`.",
        ]
    )
